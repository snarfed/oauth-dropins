"""Google Sign-In OAuth drop-in.

Google Sign-In API docs: https://developers.google.com/identity/protocols/OAuth2WebServer
Python API client docs: https://developers.google.com/api-client-library/python/
requests-oauthlib docs:
  https://requests-oauthlib.readthedocs.io/
  https://requests-oauthlib.readthedocs.io/en/latest/examples/google.html
"""
import logging

from google.cloud import ndb
from requests_oauthlib import OAuth2Session

from . import handlers, models
from .webutil import handlers as webutil_handlers
from .webutil import util
from .webutil.util import json_dumps, json_loads

GOOGLE_CLIENT_ID = util.read('google_client_id')
GOOGLE_CLIENT_SECRET = util.read('google_client_secret')
AUTH_CODE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
ACCESS_TOKEN_URL = 'https://www.googleapis.com/oauth2/v4/token'
# Discovered on 1/30/2019 from:
#   https://accounts.google.com/.well-known/openid-configuration
# Background: https://developers.google.com/identity/protocols/OpenIDConnect#discovery
OPENID_CONNECT_USERINFO = 'https://openidconnect.googleapis.com/v1/userinfo'


class GoogleUser(models.BaseAuth):
  """An authenticated Google user.

  Provides methods that return information about this user and make OAuth-signed
  requests to Google APIs. Stores OAuth credentials in the datastore. See
  models.BaseAuth for usage details.

  To make Google API calls: https://google-auth.readthedocs.io/
  """
  user_json = ndb.TextProperty()
  token_json = ndb.TextProperty()

  def site_name(self):
    return 'Google'

  def user_display_name(self):
    """Returns the user's name."""
    return json_loads(self.user_json).get('name') or 'unknown'

  def access_token(self):
    """Returns the OAuth access token string."""
    return json_loads(self.token_json)['access_token']


class Scopes(object):
  # OAuth/OpenID Connect scopes:
  #   https://developers.google.com/+/web/api/rest/oauth#authorization-scopes
  # Google scopes:
  #   https://developers.google.com/identity/protocols/googlescopes
  DEFAULT_SCOPE = 'openid https://www.googleapis.com/auth/userinfo.profile'
  SCOPE_SEPARATOR = ' '


class StartHandler(Scopes, handlers.StartHandler):
  """Starts the OAuth flow."""
  NAME = 'google_signin'
  LABEL = 'Google'

  handle_exception = webutil_handlers.handle_exception

  def redirect_url(self, state=None):
    assert GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, \
            "Please fill in the google_client_id and google_client_secret files in your app's root directory."

    session = OAuth2Session(GOOGLE_CLIENT_ID, scope=self.scope,
                            redirect_uri=self.to_url())
    auth_url, state = session.authorization_url(
      AUTH_CODE_URL, state=state,
      # ask for a refresh token so we can get an access token offline
      access_type='offline', prompt='consent',
      # https://developers.google.com/accounts/docs/OAuth2WebServer#incrementalAuth
      include_granted_scopes='true')
    return auth_url


class CallbackHandler(Scopes, handlers.CallbackHandler):
  """Finishes the OAuth flow."""

  def get(self):
    # handle errors
    state = self.request.get('state')
    error = self.request.get('error')
    desc = self.request.get('error_description')
    if error:
      msg = 'Error: %s: %s' % (error, desc)
      logging.info(msg)
      if error == 'access_denied':
        return self.finish(None, state=state)
      else:
        raise exc.HTTPBadRequest(msg)

    # extract auth code and request access token
    session = OAuth2Session(GOOGLE_CLIENT_ID, scope=self.scope,
                            redirect_uri=self.request.path_url)
    session.fetch_token(ACCESS_TOKEN_URL,
                        client_secret=GOOGLE_CLIENT_SECRET,
                        authorization_response=self.request.url)

    # get OpenID Connect user info
    # https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims
    resp = session.get(OPENID_CONNECT_USERINFO)
    try:
      resp.raise_for_status()
    except BaseException as e:
      util.interpret_http_exception(e)
      raise

    user_json = json_loads(resp.text)
    logging.info('Got one person', user_json)

    user = GoogleUser(id=user_json['sub'], user_json=json_dumps(user_json),
                      token_json=json_dumps(session.token))
    user.put()
    self.finish(user, state=state)
