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

from webutil import util
from webutil import handlers as webutil_handlers

from google.appengine.ext import ndb
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

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds an OAuth signature.
    """
    return TwitterAuth.signed_urlopen(url, self.token_key, self.token_secret,
                                      **kwargs)

  @staticmethod
  def auth_header(url, token_key, token_secret):
    """Generates an Authorization header and returns it in a header dict.

    Args:
      url: string
      token_key: string
      token_secret: string

    Returns: single element dict with key 'Authorization'
    """
    parsed = urlparse.urlparse(url)
    url_without_query = urlparse.urlunparse(list(parsed[0:4]) + ['', ''])
    header = {}
    auth = TwitterAuth.tweepy_auth(token_key, token_secret)
    auth.apply_auth(url_without_query, 'GET', header,
                    dict(urlparse.parse_qsl(parsed.query)))
    logging.debug(
      'Generated Authorization header from access token key %s... and secret %s...',
      token_key[:4], token_secret[:4])
      # header.get('Authorization'))
    return header

  @staticmethod
  def signed_urlopen(url, token_key, token_secret, headers=None, **kwargs):
    """Wraps urllib2.urlopen() and adds an OAuth signature.
    """
    if headers is None:
      headers = {}
    headers.update(TwitterAuth.auth_header(url, token_key, token_secret))
    logging.debug('Fetching %s', url)
    return urllib2.urlopen(urllib2.Request(url, headers=headers), **kwargs)

  def tweepy_api(self):
    """Returns a tweepy.API.
    """
    return tweepy.API(TwitterAuth.tweepy_auth(self.token_key, self.token_secret))

  @staticmethod
  def tweepy_auth(token_key, token_secret):
    """Returns a tweepy.OAuthHandler.
    """
    auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                               appengine_config.TWITTER_APP_SECRET)
    # make sure token key and secret aren't unicode because python's hmac
    # module (used by tweepy/oauth.py) expects strings.
    # http://stackoverflow.com/questions/11396789
    # fixed in https://github.com/tweepy/tweepy/commit/5a22bf73ccf7fae3d2b10314ce7f8eef067fee7a
    auth.set_access_token(str(token_key), str(token_secret))
    return auth


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
    auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                               appengine_config.TWITTER_APP_SECRET,
                               self.to_url(state=state))
    auth_url = auth.get_authorization_url()

    # store the request token for later use in the callback handler
    models.OAuthRequestToken(id=auth.request_token.key,
                             token_secret=auth.request_token.secret).put()
    logging.info('Generated request token, redirecting to Twitter: %s', auth_url)
    return auth_url


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

    # Rebuild the auth handler
    auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                               appengine_config.TWITTER_APP_SECRET)
    auth.set_request_token(request_token.key.string_id(), request_token.token_secret)

    # Fetch the access token
    access_token = auth.get_access_token(oauth_verifier)
    user_json = TwitterAuth.signed_urlopen(API_ACCOUNT_URL,
                                           access_token.key,
                                           access_token.secret).read()
    username = json.loads(user_json)['screen_name']

    auth = TwitterAuth(id=username,
                       token_key=access_token.key,
                       token_secret=access_token.secret,
                       user_json=user_json)
    auth.put()
    self.finish(auth, state=self.request.get('state'))
