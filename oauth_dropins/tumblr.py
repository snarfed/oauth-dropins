"""Tumblr OAuth drop-in.

API docs:
http://www.tumblr.com/docs/en/api/v2
http://www.tumblr.com/oauth/apps
"""

import json
import logging

import appengine_config
import handlers
import models
import tumblpy
from webob import exc

from google.appengine.ext import ndb
from webutil import handlers as webutil_handlers
from webutil import util


class TumblrAuth(models.BaseAuth):
  """An authenticated Tumblr user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the Tumblr API. Stores OAuth credentials in the datastore. See
  models.BaseAuth for usage details.

  Tumblr-specific details: implements api() but not urlopen() or http(). api()
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
    return self.key.string_id()

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
    assert (appengine_config.TUMBLR_APP_KEY and
            appengine_config.TUMBLR_APP_SECRET), (
      "Please fill in the tumblr_app_key and tumblr_app_secret files in "
      "your app's root directory.")
    return tumblpy.Tumblpy(app_key=appengine_config.TUMBLR_APP_KEY,
                           app_secret=appengine_config.TUMBLR_APP_SECRET,
                           oauth_token=key, oauth_token_secret=secret)


def handle_exception(self, e, debug):
  """Exception handler that handles Tweepy errors.
  """
  if isinstance(e, tumblpy.TumblpyError):
      logging.exception('OAuth error')
      raise exc.HTTPBadRequest(e)
  else:
    return webutil_handlers.handle_exception(self, e, debug)


class StartHandler(handlers.StartHandler):
  """Starts Tumblr auth. Requests an auth code and expects a redirect back.
  """
  handle_exception = handle_exception

  def redirect_url(self, state=None):
    assert (appengine_config.TUMBLR_APP_KEY and
            appengine_config.TUMBLR_APP_SECRET), (
      "Please fill in the tumblr_app_key and tumblr_app_secret files in "
      "your app's root directory.")
    tp = tumblpy.Tumblpy(app_key=appengine_config.TUMBLR_APP_KEY,
                         app_secret=appengine_config.TUMBLR_APP_SECRET)
    auth_props = tp.get_authentication_tokens(
      callback_url=self.request.host_url + self.to_path)

    # store the request token for later use in the callback handler
    models.OAuthRequestToken(id=auth_props['oauth_token'],
                             token_secret=auth_props['oauth_token_secret'],
                             state=state).put()
    return auth_props['auth_url']


class CallbackHandler(handlers.CallbackHandler):
  """OAuth callback. Fetches the user's blogs and stores the credentials.
  """
  handle_exception = handle_exception

  def get(self):
    verifier = self.request.get('oauth_verifier')
    request_token_key = self.request.get('oauth_token')
    if not verifier or not request_token_key:
      # user declined
      self.finish(None)
      return

    # look up the request token
    request_token = models.OAuthRequestToken.get_by_id(request_token_key)
    if request_token is None:
      raise exc.HTTPBadRequest('Invalid oauth_token: %s' % request_token_key)

    # generate and store the final token
    tp = tumblpy.Tumblpy(app_key=appengine_config.TUMBLR_APP_KEY,
                         app_secret=appengine_config.TUMBLR_APP_SECRET,
                         oauth_token=request_token_key,
                         oauth_token_secret=request_token.token_secret)
    auth_token = tp.get_authorized_tokens(verifier)
    auth_token_key = auth_token['oauth_token']
    auth_token_secret = auth_token['oauth_token_secret']

    # get the user's blogs
    # http://www.tumblr.com/docs/en/api/v2#user-methods
    tp = TumblrAuth._api_from_token(auth_token_key, auth_token_secret)
    logging.debug('Fetching user/info')
    try:
      resp = tp.post('user/info')
    except BaseException, e:
      util.interpret_http_exception(e)
      raise
    logging.debug('Got: %s', resp)
    user = resp['user']

    auth = TumblrAuth(id=user['name'],
                      token_key=auth_token_key,
                      token_secret=auth_token_secret,
                      user_json=json.dumps(resp))
    auth.put()
    self.finish(auth, state=request_token.state)
