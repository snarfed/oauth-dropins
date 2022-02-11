"""Tumblr OAuth drop-in.

API docs:
http://www.tumblr.com/docs/en/api/v2
http://www.tumblr.com/oauth/apps
"""
import logging
import urllib.parse

from flask import request
from google.cloud import ndb
import tumblpy

from . import views, models
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

TUMBLR_APP_KEY = util.read('tumblr_app_key')
TUMBLR_APP_SECRET = util.read('tumblr_app_secret')


class TumblrAuth(models.BaseAuth):
  """An authenticated Tumblr user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the Tumblr API. Stores OAuth credentials in the datastore. See
  models.BaseAuth for usage details.

  Tumblr-specific details: implements api() but not urlopen(). api()
  returns a tumblpy.Tumblpy. The datastore entity key name is the Tumblr
  username.
  """
  # access token
  token_key = ndb.StringProperty(required=True)
  token_secret = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Tumblr'

  def user_display_name(self):
    """Returns the username.
    """
    return self.key_id()

  def access_token(self):
    """Returns the OAuth access token as a (string key, string secret) tuple.
    """
    return (self.token_key, self.token_secret)

  def _api(self):
    """Returns a tumblpy.Tumblpy.
    """
    return TumblrAuth._api_from_token(self.token_key, self.token_secret)

  @staticmethod
  def _api_from_token(key, secret):
    """Returns a tumblpy.Tumblpy.
    """
    assert TUMBLR_APP_KEY and TUMBLR_APP_SECRET, \
      "Please fill in the tumblr_app_key and tumblr_app_secret files in your app's root directory."
    return tumblpy.Tumblpy(app_key=TUMBLR_APP_KEY,
                           app_secret=TUMBLR_APP_SECRET,
                           oauth_token=key, oauth_token_secret=secret)


class Start(views.Start):
  """Starts Tumblr auth. Requests an auth code and expects a redirect back.
  """
  NAME = 'tumblr'
  LABEL = 'Tumblr'

  def redirect_url(self, state=None):
    assert TUMBLR_APP_KEY and TUMBLR_APP_SECRET, \
      "Please fill in the tumblr_app_key and tumblr_app_secret files in your app's root directory."
    tp = tumblpy.Tumblpy(app_key=TUMBLR_APP_KEY,
                         app_secret=TUMBLR_APP_SECRET)
    auth_props = tp.get_authentication_tokens(
      callback_url=urllib.parse.urljoin(request.host_url, self.to_path))

    # store the request token for later use in the callback view
    models.OAuthRequestToken(id=auth_props['oauth_token'],
                             token_secret=auth_props['oauth_token_secret'],
                             state=state).put()
    return auth_props['auth_url']

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args,
      input_style='background-color: #406784; padding: 10px',
      **kwargs)


class Callback(views.Callback):
  """OAuth callback. Fetches the user's blogs and stores the credentials.
  """
  def dispatch_request(self):
    verifier = request.values.get('oauth_verifier')
    request_token_key = request.values.get('oauth_token')
    if not verifier or not request_token_key:
      # user declined
      return self.finish(None)

    # look up the request token
    request_token = models.OAuthRequestToken.get_by_id(request_token_key)
    if request_token is None:
      flask_util.error(f'Invalid oauth_token: {request_token_key}')

    # generate and store the final token
    tp = tumblpy.Tumblpy(app_key=TUMBLR_APP_KEY,
                         app_secret=TUMBLR_APP_SECRET,
                         oauth_token=request_token_key,
                         oauth_token_secret=request_token.token_secret)
    auth_token = tp.get_authorized_tokens(verifier)
    auth_token_key = auth_token['oauth_token']
    auth_token_secret = auth_token['oauth_token_secret']

    # get the user's blogs
    # http://www.tumblr.com/docs/en/api/v2#user-methods
    tp = TumblrAuth._api_from_token(auth_token_key, auth_token_secret)
    logger.debug('Fetching user/info')
    try:
      resp = tp.post('user/info')
    except BaseException as e:
      util.interpret_http_exception(e)
      raise
    logger.debug(f'Got: {resp}')
    user = resp['user']

    auth = TumblrAuth(id=user['name'],
                      token_key=auth_token_key,
                      token_secret=auth_token_secret,
                      user_json=json_dumps(resp))
    auth.put()
    return self.finish(auth, state=request_token.state)
