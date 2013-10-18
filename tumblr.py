"""Tumblr OAuth drop-in.

API docs:
http://www.tumblr.com/docs/en/api/v2
http://www.tumblr.com/oauth/apps
"""

import json
import logging
import urllib
import urlparse

import appengine_config
import handlers
import models
import tumblpy
from webob import exc
from webutil import util

from google.appengine.ext import db
from google.appengine.ext.webapp import template
import webapp2


assert (appengine_config.TUMBLR_APP_KEY and
        appengine_config.TUMBLR_APP_SECRET), (
        "Please fill in the tumblr_app_key and tumblr_app_secret files in "
        "your app's root directory.")


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
  token_key = db.StringProperty(required=True)
  token_secret = db.StringProperty(required=True)
  user_json = db.TextProperty(required=True)

  def site_name(self):
    return 'Tumblr'

  def user_display_name(self):
    """Returns the username.
    """
    return self.key().name()

  def _api(self):
    """Returns a tumblpy.Tumblpy.
    """
    return TumblrAuth._api_from_token(self.token_key, self.token_secret)

  @staticmethod
  def _api_from_token(key, secret):
    """Returns a tumblpy.Tumblpy.
    """
    return tumblpy.Tumblpy(app_key=appengine_config.TUMBLR_APP_KEY,
                           app_secret=appengine_config.TUMBLR_APP_SECRET,
                           oauth_token=key, oauth_token_secret=secret)


class StartHandler(handlers.StartHandler):
  """Starts Tumblr auth. Requests an auth code and expects a redirect back.
  """

  def redirect_url(self, state=''):
    tp = tumblpy.Tumblpy(app_key=appengine_config.TUMBLR_APP_KEY,
                         app_secret=appengine_config.TUMBLR_APP_SECRET)
    auth_props = tp.get_authentication_tokens(
      callback_url=self.request.host_url + self.to_path)

    # store the request token for later use in the callback handler
    models.OAuthRequestToken(key_name=auth_props['oauth_token'],
                             token_secret=auth_props['oauth_token_secret']).save()
    return auth_props['auth_url']


class CallbackHandler(handlers.CallbackHandler):
  """OAuth callback. Fetches the user's blogs and stores the credentials.
  """

  def get(self):
    # lookup the request token
    request_token_key = self.request.get('oauth_token')
    request_token = models.OAuthRequestToken.get_by_key_name(request_token_key)
    if request_token is None:
      raise exc.HTTPBadRequest('Invalid oauth_token: %s' % request_token_key)

    # generate and store the final token
    tp = tumblpy.Tumblpy(app_key=appengine_config.TUMBLR_APP_KEY,
                         app_secret=appengine_config.TUMBLR_APP_SECRET,
                         oauth_token=request_token_key,
                         oauth_token_secret=request_token.token_secret)
    auth_token = tp.get_authorized_tokens(self.request.params['oauth_verifier'])
    auth_token_key = auth_token['oauth_token']
    auth_token_secret = auth_token['oauth_token_secret']

    # get the user's blogs
    # http://www.tumblr.com/docs/en/api/v2#user-methods
    tp = TumblrAuth._api_from_token(auth_token_key, auth_token_secret)
    logging.debug('Fetching user/info')
    resp = tp.post('user/info')
    logging.debug('Got: %s', resp)
    user = resp['user']

    auth = TumblrAuth(key_name=user['name'],
                      token_key=auth_token_key,
                      token_secret=auth_token_secret,
                      user_json=json.dumps(resp))
    auth.save()
    self.finish(auth, state=self.request.get('state'))
