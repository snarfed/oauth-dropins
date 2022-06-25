"""Twitter OAuth drop-in.

TODO: port to
http://code.google.com/p/oauth/source/browse/#svn%2Fcode%2Fpython . tweepy is
just a wrapper around that anyway.
"""
import logging

from flask import request
from google.cloud import ndb
import tweepy

from . import models, twitter_auth, views
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

API_ACCOUNT_URL = 'https://api.twitter.com/1.1/account/verify_credentials.json'


class TwitterAuth(models.BaseAuth):
  """An authenticated Twitter user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the Twitter v1.1 API. Stores OAuth credentials in the datastore.
  See models.BaseAuth for usage details.

  Twitter-specific details: implements api(), get(), and post(). api() returns a
  tweepy.API; get() and post() wrap the corresponding requests methods. The
  datastore entity key name is the Twitter username.
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
    return self.key_id()

  def access_token(self):
    """Returns the OAuth access token as a (string key, string secret) tuple.
    """
    return (self.token_key, self.token_secret)

  def urlopen(self, url, **kwargs):
    """Wraps urllib.request.urlopen() and adds an OAuth signature.
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
    except BaseException as e:
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
    except BaseException as e:
      util.interpret_http_exception(e)
      raise
    return resp

  def api(self):
    """Returns a tweepy.API.
    """
    return tweepy.API(twitter_auth.tweepy_auth(self.token_key, self.token_secret))


class Start(views.Start):
  """Starts three-legged OAuth with Twitter.

  Fetches an OAuth request token, then redirects to Twitter's auth page to
  request an access token.

  Attributes:
    access_type: optional, 'read' or 'write'. Passed through to Twitter as
      x_auth_access_type. If the twitter app has read/write or read/write/dm
      permissions, this lets you request a read-only token. Details:
      https://dev.twitter.com/docs/api/1/post/oauth/request_token
  """
  NAME = 'twitter'
  LABEL = 'Twitter'

  def __init__(self, to_path, scopes=None, access_type=None):
    super().__init__(to_path, scopes=scopes)
    assert access_type in (None, 'read', 'write'), \
        f'access_type must be "read" or "write"; got {access_type!r}'
    self.access_type = access_type

  def redirect_url(self, state=None):
    assert twitter_auth.TWITTER_APP_KEY and twitter_auth.TWITTER_APP_SECRET, \
      "Please fill in the twitter_app_key and twitter_app_secret files in your app's root directory."
    auth = tweepy.OAuth1UserHandler(twitter_auth.TWITTER_APP_KEY,
                                    twitter_auth.TWITTER_APP_SECRET,
                                    callback=self.to_url(state=state))

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

    # store the request token for later use in the callback view
    models.OAuthRequestToken(id=auth.request_token['oauth_token'],
                             token_secret=auth.request_token['oauth_token_secret']
                             ).put()
    logger.info(f'Generated request token, redirecting to Twitter: {auth_url}')
    return auth_url


class Callback(views.Callback):
  """The OAuth callback. Fetches an access token and redirects to the front page.
  """
  def dispatch_request(self):
    # https://dev.twitter.com/docs/application-permission-model
    if request.values.get('denied'):
      return self.finish(None, state=request.values.get('state'))
    oauth_token = request.values.get('oauth_token', None)
    oauth_verifier = request.values.get('oauth_verifier', None)
    if oauth_token is None:
      flask_util.error('Missing required query parameter oauth_token.')

    # Lookup the request token
    request_token = models.OAuthRequestToken.get_by_id(oauth_token)
    if request_token is None:
      flask_util.error(f'Invalid oauth_token: {oauth_token}')

    # Rebuild the auth view
    auth = tweepy.OAuth1UserHandler(twitter_auth.TWITTER_APP_KEY,
                                    twitter_auth.TWITTER_APP_SECRET)
    auth.request_token = {'oauth_token': request_token.key.string_id(),
                          'oauth_token_secret': request_token.token_secret}

    # Fetch the access token
    access_token_key, access_token_secret = auth.get_access_token(oauth_verifier)
    user_json = twitter_auth.signed_urlopen(API_ACCOUNT_URL,
                                            access_token_key,
                                            access_token_secret).read()
    username = json_loads(user_json)['screen_name']

    auth = TwitterAuth(id=username,
                       token_key=access_token_key,
                       token_secret=access_token_secret,
                       user_json=user_json)
    auth.put()
    return self.finish(auth, state=request.values.get('state'))
