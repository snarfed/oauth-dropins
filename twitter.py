"""Twitter OAuth drop-in.

TODO: port to
http://code.google.com/p/oauth/source/browse/#svn%2Fcode%2Fpython . tweepy is
just a wrapper around that anyway.
"""

import json
import logging
from webob import exc

import appengine_config
import handlers
import models
import tweepy
import requests
import twitter_auth

from webutil import util
from webutil import handlers as webutil_handlers

from google.appengine.ext import ndb
import webapp2


API_ACCOUNT_URL = 'https://api.twitter.com/1.1/account/verify_credentials.json'


class TwitterAuth(models.BaseAuth):
  """An authenticated Twitter user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the Twitter v1.1 API. Stores OAuth credentials in the datastore.
  See models.BaseAuth for usage details.

  Twitter-specific details: implements api(), get(), and post() but not http().
  api() returns a tweepy.API; get() and post() wrap the corresponding requests
  methods. The datastore entity key name is the Twitter username.
  """
  # access token
  token_key = ndb.StringProperty(required=True)
  token_secret = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Twitter'

  def user_display_name(self):
    """Returns the username.
    """
    return self.key.string_id()

  def access_token(self):
    """Returns the OAuth access token as a (string key, string secret) tuple.
    """
    return (self.token_key, self.token_secret)

  def get(self, *args, **kwargs):
    """Wraps requests.get() and adds an OAuth signature.
    """
    oauth1 = twitter_auth.auth(self.token_key, self.token_secret)
    resp = requests.get(*args, auth=oauth1, **kwargs)
    resp.raise_for_status()
    return resp

  def post(self, *args, **kwargs):
    """Wraps requests.post() and adds an OAuth signature.
    """
    oauth1 = twitter_auth.auth(self.token_key, self.token_secret)
    resp = requests.post(*args, auth=oauth1, **kwargs)
    resp.raise_for_status()
    return resp

  def api(self):
    """Returns a tweepy.API.
    """
    return tweepy.API(twitter_auth.tweepy_auth(self.token_key, self.token_secret))

def handle_exception(self, e, debug):
  """Exception handler that handles Tweepy errors.
  """
  if isinstance(e, tweepy.TweepError):
      logging.exception('OAuth error')
      raise exc.HTTPBadRequest(e)
  else:
    return webutil_handlers.handle_exception(self, e, debug)


class StartHandler(handlers.StartHandler):
  """Starts three-legged OAuth with Twitter.

  Fetches an OAuth request token, then redirects to Twitter's auth page to
  request an access token.
  """
  handle_exception = handle_exception

  def redirect_url(self, state=None):
    assert (appengine_config.TWITTER_APP_KEY and
            appengine_config.TWITTER_APP_SECRET), (
      "Please fill in the twitter_app_key and twitter_app_secret files in "
      "your app's root directory.")
    auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                               appengine_config.TWITTER_APP_SECRET,
                               self.to_url(state=state))

    # signin_with_twitter=True returns /authenticate instead of /authorize so
    # that Twitter doesn't prompt the user for approval if they've already
    # approved. Background: https://dev.twitter.com/discussions/1253
    #
    # Requires "Allow this application to be used to Sign in with Twitter"
    # to be checked in the app's settings on https://apps.twitter.com/
    auth_url = auth.get_authorization_url(signin_with_twitter=True)

    # store the request token for later use in the callback handler
    print `auth.request_token`
    models.OAuthRequestToken(id=auth.request_token['oauth_token'],
                             token_secret=auth.request_token['oauth_token_secret']
                             ).put()
    logging.info('Generated request token, redirecting to Twitter: %s', auth_url)

    # app engine requires header values (ie Location for redirects) to be str,
    # not unicode.
    return str(auth_url)


class CallbackHandler(handlers.CallbackHandler):
  """The OAuth callback. Fetches an access token and redirects to the front page.
  """
  handle_exception = handle_exception

  def get(self):
    # https://dev.twitter.com/docs/application-permission-model
    if self.request.get('denied'):
      self.finish(None, state=self.request.get('state'))
      return

    oauth_token = self.request.get('oauth_token', None)
    oauth_verifier = self.request.get('oauth_verifier', None)
    if oauth_token is None:
      raise exc.HTTPBadRequest('Missing required query parameter oauth_token.')

    # Lookup the request token
    request_token = models.OAuthRequestToken.get_by_id(oauth_token)
    if request_token is None:
      raise exc.HTTPBadRequest('Invalid oauth_token: %s' % oauth_token)

    # Rebuild the auth handler and fetch the access token
    handler = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                                  appengine_config.TWITTER_APP_SECRET)
    handler.request_token = {'oauth_token': request_token.key.string_id(),
                             'oauth_token_secret': request_token.token_secret}
    access_token_key, access_token_secret = handler.get_access_token(oauth_verifier)

    # Fetch user info and username
    resp = requests.get(API_ACCOUNT_URL, auth=twitter_auth.oauth1(access_token_key,
                                                                  access_token_secret))
    resp.raise_for_status()
    username = json.loads(resp.text)['screen_name']
    auth = TwitterAuth(id=username,
                       token_key=access_token_key,
                       token_secret=access_token_secret,
                       user_json=resp.text)
    auth.put()
    self.finish(auth, state=self.request.get('state'))
