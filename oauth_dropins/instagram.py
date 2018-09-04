"""Instagram OAuth drop-in.

Instagram API docs: http://instagram.com/developer/endpoints/

Almost identical to Facebook, except the access token request has `code`
and `grant_type` query parameters instead of just `auth_code`, the response
has a `user` object instead of `id`, and the call to GET_ACCESS_TOKEN_URL
is a POST instead of a GET.
TODO: unify them.
"""

import json
import logging
import urllib

import appengine_config
import facebook  # we reuse facebook.CallbackHandler.handle_error()
import handlers
import models
from webutil import util

from google.appengine.ext import ndb
from webob import exc


# instagram api url templates. can't (easily) use urllib.urlencode() because i
# want to keep the %(...)s placeholders as is and fill them in later in code.
# the str() is since WSGI middleware chokes on unicode redirect URLs :/
GET_AUTH_CODE_URL = str('&'.join((
    'https://api.instagram.com/oauth/authorize?',
    'client_id=%(client_id)s',
    'scope=%(scope)s',
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

  Instagram-specific details: implements urlopen() but not api() nor
  http().  The key name is the Instagram username.
  """
  auth_code = ndb.StringProperty(required=True)
  access_token_str = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Instagram'

  def user_display_name(self):
    """Returns the Instagram username.
    """
    return self.key.string_id()

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds OAuth credentials to the request.
    """
    return models.BaseAuth.urlopen_access_token(url, self.access_token_str,
                                                **kwargs)


class StartHandler(handlers.StartHandler):
  """Starts Instagram auth. Requests an auth code and expects a redirect back.
  """
  DEFAULT_SCOPE = 'basic'

  def redirect_url(self, state=None):
    assert (appengine_config.INSTAGRAM_CLIENT_ID and
            appengine_config.INSTAGRAM_CLIENT_SECRET), (
      "Please fill in the instagram_client_id and instagram_client_secret "
      "files in your app's root directory.")
    # http://instagram.com/developer/authentication/
    return GET_AUTH_CODE_URL % {
      'client_id': appengine_config.INSTAGRAM_CLIENT_ID,
      # instagram uses + instead of , to separate scopes
      # http://instagram.com/developer/authentication/#scope
      # also, the str() is since WSGI middleware chokes on unicode redirect URLs :/
      'scope': str(self.scope.replace(',', '+')),
      # TODO: CSRF protection identifier.
      'redirect_uri': urllib.quote_plus(self.to_url(state=state)),
    }


class CallbackHandler(handlers.CallbackHandler):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """

  def get(self):
    if facebook.CallbackHandler.handle_error(self):
      return

    # http://instagram.com/developer/authentication/
    auth_code = util.get_required_param(self, 'code')
    data = {
      'client_id': appengine_config.INSTAGRAM_CLIENT_ID,
      'client_secret': appengine_config.INSTAGRAM_CLIENT_SECRET,
      'code': auth_code,
      'redirect_uri': self.request_url_with_state(),
      'grant_type': 'authorization_code',
    }

    try:
      resp = util.urlopen(GET_ACCESS_TOKEN_URL, data=urllib.urlencode(data)).read()
    except BaseException, e:
      util.interpret_http_exception(e)
      raise

    try:
      data = json.loads(resp)
    except (ValueError, TypeError):
      logging.exception('Bad response:\n%s', resp)
      raise exc.HttpBadRequest('Bad Instagram response to access token request')

    if 'error_type' in resp:
      error_class = exc.status_map[data.get('code', 500)]
      raise error_class(data.get('error_message'))

    access_token = data['access_token']
    username = data['user']['username']

    auth = InstagramAuth(id=username,
                         auth_code=auth_code,
                         access_token_str=access_token,
                         user_json=json.dumps(data['user']))
    auth.put()
    self.finish(auth, state=self.request.get('state'))
