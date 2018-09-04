"""Twitter OAuth drop-in.

TODO: port to
http://code.google.com/p/oauth/source/browse/#svn%2Fcode%2Fpython . tweepy is
just a wrapper around that anyway.
"""
from future.utils import native_str

import json
import logging
from webob import exc

import appengine_config
import handlers
import models
import tweepy
import twitter_auth

from webutil import handlers as webutil_handlers
from webutil import util

from google.appengine.ext import ndb


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

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds an OAuth signature.
    """
    return twitter_auth.signed_urlopen(url, self.token_key, self.token_secret,
                                       **kwargs)

  def get(self, *args, **kwargs):
    """Wraps requests.get() and adds an OAuth signature.
    """
    oauth1 = twitter_auth.auth(self.token_key, self.token_secret)
    resp = util.requests_get(*args, auth=oauth1, **kwargs)
    try:
      resp.raise_for_status()
    except BaseException, e:
      util.interpret_http_exception(e)
      raise
    return resp

  def post(self, *args, **kwargs):
    """Wraps requests.post() and adds an OAuth signature.
    """
    oauth1 = twitter_auth.auth(self.token_key, self.token_secret)
    resp = util.requests_post(*args, auth=oauth1, **kwargs)
    try:
      resp.raise_for_status()
    except BaseException, e:
      util.interpret_http_exception(e)
      raise
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

  Attributes:
    access_type: optional, 'read' or 'write'. Passed through to Twitter as
      x_auth_access_type. If the twitter app has read/write or read/write/dm
      permissions, this lets you request a read-only token. Details:
      https://dev.twitter.com/docs/api/1/post/oauth/request_token
  """
  handle_exception = handle_exception

  @classmethod
  def to(cls, path, scopes=None, access_type=None):
    assert access_type in (None, 'read', 'write'), \
        'access_type must be "read" or "write"; got %r' % access_type
    handler = super(StartHandler, cls).to(path, scopes=scopes)
    handler.access_type = access_type
    return handler

  def redirect_url(self, state=None):
    assert (appengine_config.TWITTER_APP_KEY and
            appengine_config.TWITTER_APP_SECRET), (
      "Please fill in the twitter_app_key and twitter_app_secret files in "
      "your app's root directory.")
    auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                               appengine_config.TWITTER_APP_SECRET,
                               native_str(self.to_url(state=state)))

    # signin_with_twitter=True returns /authenticate instead of /authorize so
    # that Twitter doesn't prompt the user for approval if they've already
    # approved. Background: https://dev.twitter.com/discussions/1253
    #
    # Requires "Allow this application to be used to Sign in with Twitter"
    # to be checked in the app's settings on https://apps.twitter.com/
    #
    # Also, there's a Twitter API bug that makes /authenticate and
    # x_auth_access_type not play nice with each other. Work around that by only
    # using /authenticate if access_type isn't set.
    # https://dev.twitter.com/discussions/21281
    auth_url = auth.get_authorization_url(
      signin_with_twitter=not self.access_type, access_type=self.access_type)

    # store the request token for later use in the callback handler
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

    # Rebuild the auth handler
    auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                               appengine_config.TWITTER_APP_SECRET)
    auth.request_token = {'oauth_token': request_token.key.string_id(),
                          'oauth_token_secret': request_token.token_secret}

    # Fetch the access token
    access_token_key, access_token_secret = auth.get_access_token(oauth_verifier)
    user_json = twitter_auth.signed_urlopen(API_ACCOUNT_URL,
                                            access_token_key,
                                            access_token_secret).read()
    username = json.loads(user_json)['screen_name']

    auth = TwitterAuth(id=username,
                       token_key=access_token_key,
                       token_secret=access_token_secret,
                       user_json=user_json)
    auth.put()
    self.finish(auth, state=self.request.get('state'))
