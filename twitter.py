"""Twitter OAuth drop-in.

TODO: port to
http://code.google.com/p/oauth/source/browse/#svn%2Fcode%2Fpython . tweepy is
just a wrapper around that anyway.
"""

import json
import logging
import urllib
import urllib2
import urlparse
from webob import exc

import appengine_config
import handlers
import models
import tweepy

from webutil.models import KeyNameModel
from webutil import util

from google.appengine.ext import db
import webapp2


assert (appengine_config.TWITTER_APP_KEY and
        appengine_config.TWITTER_APP_SECRET), (
        "Please fill in the twitter_app_key and twitter_app_secret files in "
        "your app's root directory.")

API_ACCOUNT_URL = 'https://api.twitter.com/1.1/account/verify_credentials.json'


class TwitterAuth(models.BaseAuth):
  """An authenticated Twitter user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the Twitter v1.1 API. Stores OAuth credentials in the datastore.
  See models.BaseAuth for usage details.

  Twitter-specific details: implements urlopen() and api() but not http(). api()
  returns a tweepy.API. The datastore entity key name is the Twitter username.
  """
  # access token
  token_key = db.StringProperty(required=True)
  token_secret = db.StringProperty(required=True)
  user_json = db.TextProperty(required=True)

  def site_name(self):
    return 'Twitter'

  def user_display_name(self):
    """Returns the username.
    """
    return self.key().name()

  def access_token(self):
    """Returns the OAuth access token as a (string key, string secret) tuple.
    """
    return (self.token_key, self.token_secret)

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds an OAuth signature.
    """
    return TwitterAuth.signed_urlopen(url, self.token_key, self.token_secret,
                                      **kwargs)

  @staticmethod
  def signed_urlopen(url, token_key, token_secret, **kwargs):
    """Wraps urllib2.urlopen() and adds an OAuth signature.
    """
    parsed = urlparse.urlparse(url)
    url_without_query = urlparse.urlunparse(list(parsed[0:4]) + ['', ''])
    headers = {}
    auth = TwitterAuth._auth(token_key, token_secret)
    auth.apply_auth(url_without_query, 'GET', headers,
                    dict(urlparse.parse_qsl(parsed.query)))
    logging.debug('Populated Authorization header from access token: %s',
                  headers.get('Authorization'))
    logging.debug('Fetching %s', url)
    return urllib2.urlopen(urllib2.Request(url, headers=headers), **kwargs)

  def _api(self):
    """Returns a tweepy.API.
    """
    return tweepy.API(TwitterAuth._auth(self.token_key, self.token_secret))

  @staticmethod
  def _auth(token_key, token_secret):
    """Returns a tweepy.OAuthHandler.
    """
    auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                               appengine_config.TWITTER_APP_SECRET)
    # make sure token key and secret aren't unicode because python's hmac
    # module (used by tweepy/oauth.py) expects strings.
    # http://stackoverflow.com/questions/11396789
    auth.set_access_token(str(token_key), str(token_secret))
    return auth


class StartHandler(handlers.StartHandler):
  """Starts three-legged OAuth with Twitter.

  Fetches an OAuth request token, then redirects to Twitter's auth page to
  request an access token.
  """

  def redirect_url(self, state=''):
    callback_url = '%s%s?state=%s' % (self.request.host_url, self.to_path, state)

    try:
      auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                                 appengine_config.TWITTER_APP_SECRET,
                                 callback_url)
      auth_url = auth.get_authorization_url()
    except tweepy.TweepError, e:
      msg = 'Could not create Twitter OAuth request token: '
      logging.exception(msg)
      raise exc.HTTPInternalServerError(msg + `e`)

    # store the request token for later use in the callback handler
    models.OAuthRequestToken(key_name=auth.request_token.key,
                             token_secret=auth.request_token.secret).put()
    logging.info('Generated request token, redirecting to Twitter: %s', auth_url)
    return auth_url


class CallbackHandler(handlers.CallbackHandler):
  """The OAuth callback. Fetches an access token and redirects to the front page.
  """

  def get(self):
    oauth_token = self.request.get('oauth_token', None)
    oauth_verifier = self.request.get('oauth_verifier', None)
    if oauth_token is None:
      raise exc.HTTPBadRequest('Missing required query parameter oauth_token.')

    # Lookup the request token
    request_token = models.OAuthRequestToken.get_by_key_name(oauth_token)
    if request_token is None:
      raise exc.HTTPBadRequest('Invalid oauth_token: %s' % oauth_token)

    # Rebuild the auth handler
    auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                               appengine_config.TWITTER_APP_SECRET)
    auth.set_request_token(request_token.key().name(), request_token.token_secret)

    # Fetch the access token
    try:
      access_token = auth.get_access_token(oauth_verifier)
    except tweepy.TweepError, e:
      msg = 'Twitter OAuth error, could not get access token: '
      logging.exception(msg)
      raise exc.HTTPInternalServerError(msg + `e`)

    user_json = TwitterAuth.signed_urlopen(API_ACCOUNT_URL,
                                           access_token.key,
                                           access_token.secret).read()
    username = json.loads(user_json)['screen_name']

    auth = TwitterAuth(key_name=username,
                       token_key=access_token.key,
                       token_secret=access_token.secret,
                       user_json=user_json)
    auth.save()
    self.finish(auth, state=self.request.get('state'))
