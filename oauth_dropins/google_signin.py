"""Google Sign-In OAuth drop-in.

Google Sign-In API docs: https://developers.google.com/identity/protocols/OAuth2WebServer
Python API client docs: https://developers.google.com/api-client-library/python/

WARNING: oauth2client is deprecated! google-auth is its successor.
https://google-auth.readthedocs.io/en/latest/oauth2client-deprecation.html

TODO: check that overriding CallbackHandler.finish() actually works.
"""
import json
import logging

import appengine_config

from apiclient import discovery
from apiclient.errors import HttpError
try:
  from oauth2client.appengine import CredentialsModel, OAuth2Decorator
except ImportError:
  from oauth2client.contrib.appengine import CredentialsModel, OAuth2Decorator
from oauth2client.client import OAuth2Credentials
from google.appengine.ext import db
from google.appengine.ext import ndb
import httplib2
from webutil import handlers as webutil_handlers
from webutil import util

import handlers
import models

# Discovered on 1/30/2019 from:
#   https://accounts.google.com/.well-known/openid-configuration
# Background: https://developers.google.com/identity/protocols/OpenIDConnect#discovery
OPENID_CONNECT_USERINFO = 'https://openidconnect.googleapis.com/v1/userinfo'

# global
json_service = None

# global. initialized in StartHandler.to_path().
oauth_decorator = None


class GoogleAuth(models.BaseAuth):
  """An authenticated Google user.

  Provides methods that return information about this user and make OAuth-signed
  requests to Google APIs. Stores OAuth credentials in the datastore. See
  models.BaseAuth for usage details.

  Google-specific details: implements http() but not urlopen(). The datastore
  entity key name is the Google user id. Uses credentials from the stored
  CredentialsModel since google-api-python-client stores refresh tokens there.

  To make an API call with Google's apiclient library, pass an authorized Http
  instance retrieved from this object. For example:

    service = discovery.build('calendar', 'v3', http=httplib2.Http())
    gpa = GoogleAuth.get_by_id('123')
    results = service.events().list(calendarId='primary').execute(gpa.http())

  More details: https://developers.google.com/api-client-library/python/
  """
  user_json = ndb.TextProperty()
  creds_model = ndb.KeyProperty(kind='CredentialsModel')

  # deprecated. TODO: remove
  creds_json = ndb.TextProperty()

  def site_name(self):
    return 'Google'

  def user_display_name(self):
    """Returns the user's name.
    """
    return json.loads(self.user_json)['name']

  def creds(self):
    """Returns an oauth2client.OAuth2Credentials.
    """
    if self.creds_model:
      return db.get(self.creds_model.to_old_key()).credentials
    else:
      # TODO: remove creds_json
      return OAuth2Credentials.from_json(self.creds_json)

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.creds().access_token

  def http(self, **kwargs):
    """Returns an httplib2.Http that adds OAuth credentials to requests.
    """
    http = httplib2.Http(**kwargs)
    self.creds().authorize(http)
    return http


def handle_exception(self, e, debug):
  """Exception handler that passes back HttpErrors as real HTTP errors.
  """
  if isinstance(e, HttpError):
    logging.exception(e)
    self.response.set_status(e.resp.status)
    self.response.write(str(e))
  else:
    return webutil_handlers.handle_exception(self, e, debug)


class StartHandler(handlers.StartHandler, handlers.CallbackHandler):
  """Starts and finishes the OAuth flow. The decorator handles the redirects.
  """
  handle_exception = handle_exception

  # OAuth/OpenID Connect scopes:
  #   https://developers.google.com/+/web/api/rest/oauth#authorization-scopes
  # Google scopes:
  #   https://developers.google.com/identity/protocols/googlescopes
  DEFAULT_SCOPE = 'openid profile'

  @classmethod
  def to(cls, to_path, scopes=None):
    """Override this since we need to_path to instantiate the oauth decorator.
    """
    global oauth_decorator
    if oauth_decorator is None:
      oauth_decorator = OAuth2Decorator(
        client_id=appengine_config.GOOGLE_CLIENT_ID,
        client_secret=appengine_config.GOOGLE_CLIENT_SECRET,
        scope=cls.make_scope_str(scopes, separator=' '),
        callback_path=to_path,
        # make sure we ask for a refresh token so we can use it to get an access
        # token offline. requires prompt=consent! more:
        # ~/etc/google+_oauth_credentials_debugging_for_plusstreamfeed_bridgy
        # http://googleappsdeveloper.blogspot.com.au/2011/10/upcoming-changes-to-oauth-20-endpoint.html
        access_type='offline',
        prompt='consent',
        # https://developers.google.com/accounts/docs/OAuth2WebServer#incrementalAuth
        include_granted_scopes='true')

    class Handler(cls):
      @oauth_decorator.oauth_required
      def get(self):
        assert (appengine_config.GOOGLE_CLIENT_ID and
                appengine_config.GOOGLE_CLIENT_SECRET), (
          "Please fill in the google_client_id and google_client_secret files in "
          "your app's root directory.")

        # get OpenID Connect user info
        # https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims
        try:
          _, user = oauth_decorator.http().request(OPENID_CONNECT_USERINFO)
        except BaseException as e:
          util.interpret_http_exception(e)
          raise
        user = json.loads(user.decode('utf-8'))
        logging.debug('Got one person: %r', user)

        store = oauth_decorator.credentials.store
        creds_model_key = ndb.Key(store._model.kind(), store._key_name)
        auth = GoogleAuth(id=user['sub'], creds_model=creds_model_key,
                          user_json=json.dumps(user))
        auth.put()
        self.finish(auth, state=self.request.get('state'))

      @oauth_decorator.oauth_required
      def post(self):
        return self.get()

    return Handler


class CallbackHandler(object):
  """OAuth callback handler factory.
  """
  @staticmethod
  def to(to_path):
    StartHandler.to_path = to_path
    global oauth_decorator
    assert oauth_decorator
    return oauth_decorator.callback_handler()
