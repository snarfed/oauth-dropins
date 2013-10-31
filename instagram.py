"""Instagram OAuth drop-in.

Instagram API docs: http://instagram.com/developer/endpoints/

Almost identical to Facebook, except the access token request has `code`
and `grant_type` query parameters instead of just `auth_code`, and the response
has a `user` object instead of `id`.
TODO: unify them.
"""

import json
import logging
import urllib
import urllib2
import urlparse

import appengine_config
import facebook  # we reuse facebook.CallbackHandler.handle_error()
import handlers
import models
from python_instagram.bind import InstagramAPIError
from python_instagram.client import InstagramAPI
from webob import exc
from webutil import handlers as webutil_handlers
from webutil import util

from google.appengine.ext import db
import webapp2


assert (appengine_config.INSTAGRAM_CLIENT_ID and
        appengine_config.INSTAGRAM_CLIENT_SECRET), (
  "Please fill in the instagram_client_id and instagram_client_secret files "
  "in your app's root directory.")

# instagram api url templates. can't (easily) use urllib.urlencode() because i
# want to keep the %(...)s placeholders as is and fill them in later in code.
GET_AUTH_CODE_URL = str('&'.join((
    'https://api.instagram.com/oauth/authorize?',
    'client_id=%(client_id)s',
    # redirect_uri here must be the same in the access token request!
    'redirect_uri=%(redirect_uri)s',
    'response_type=code',
    )))

GET_ACCESS_TOKEN_URL = 'https://api.instagram.com/oauth/access_token'


class InstagramAuth(models.BaseAuth):
  """An authenticated Instagram user or page.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to Instagram's HTTP-based APIs. Stores OAuth credentials
  in the datastore. See models.BaseAuth for usage details.

  Instagram-specific details: implements urlopen() and api() but not http().
  api() returns a python_instagram.InstagramAPI. The key name is the Instagram
  username.
  """
  auth_code = db.StringProperty(required=True)
  access_token_str = db.StringProperty(required=True)
  user_json = db.TextProperty(required=True)

  def site_name(self):
    return 'Instagram'

  def user_display_name(self):
    """Returns the Instagram username.
    """
    return self.key().name()

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds OAuth credentials to the request.
    """
    return BaseAuth.urlopen_access_token(url, self.access_token_str, **kwargs)

  def api(self):
    """Returns a python_instagram.InstagramAPI.

    Details: https://github.com/Instagram/python-instagram
    """
    return InstagramAPI(
      client_id=appengine_config.INSTAGRAM_CLIENT_ID,
      client_secret=appengine_config.INSTAGRAM_CLIENT_SECRET,
      access_token=self.access_token_str)


def handle_exception(self, e, debug):
  """Exception handler that converts InstagramAPIError to HTTP errors.
  """
  if isinstance(e, InstagramAPIError):
    logging.exception(e)
    self.response.set_status(e.status_code)
    self.response.write(str(e))
  else:
    return webutil_handlers.handle_exception(self, e, debug)


class StartHandler(handlers.StartHandler):
  """Starts Instagram auth. Requests an auth code and expects a redirect back.
  """
  handle_exception = handle_exception

  def redirect_url(self, state=None):
    # http://instagram.com/developer/authentication/
    return GET_AUTH_CODE_URL % {
      'client_id': appengine_config.INSTAGRAM_CLIENT_ID,
      # TODO: CSRF protection identifier.
      'redirect_uri': urllib.quote_plus(self.to_url(state=state)),
      }


class CallbackHandler(handlers.CallbackHandler):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """
  handle_exception = handle_exception

  def get(self):
    if facebook.CallbackHandler.handle_error(self):
      return

    auth_code = self.request.get('code')
    assert auth_code

    # http://instagram.com/developer/authentication/
    data = {
      'client_id': appengine_config.INSTAGRAM_CLIENT_ID,
      'client_secret': appengine_config.INSTAGRAM_CLIENT_SECRET,
      'code': auth_code,
      'redirect_uri': self.request_url_with_state(),
      'grant_type': 'authorization_code',
      }

    logging.debug('Fetching: %s with data %s', GET_ACCESS_TOKEN_URL, data)
    resp = urllib2.urlopen(GET_ACCESS_TOKEN_URL,
                           data=urllib.urlencode(data)).read()
    try:
      data = json.loads(resp)
    except ValueError, TypeError:
      logging.exception('Bad response:\n%s', resp)
      raise exc.HttpBadRequest('Bad Instagram response to access token request')

    if 'error_type' in resp:
      error_class = exc.status_map[data.get('code', 500)]
      raise error_class(data.get('error_message'))

    access_token = data['access_token']
    username = data['user']['username']

    auth = InstagramAuth(key_name=username,
                         auth_code=auth_code,
                         access_token_str=access_token,
                         user_json=json.dumps(data['user']))
    auth.save()
    self.finish(auth, state=self.request.get('state'))
