"""Google+ OAuth drop-in.

Google+ API docs: https://developers.google.com/+/api/latest/
Python API client docs: https://developers.google.com/api-client-library/python/

TODO: check that overriding CallbackHandler.finish() actually works.
"""

import json
import httplib2
import logging
import urllib

import appengine_config
import handlers
import models

from webutil import util

from apiclient import discovery
from apiclient.errors import HttpError
from oauth2client.appengine import CredentialsModel, OAuth2Decorator, StorageByKeyName
from oauth2client.client import Credentials, OAuth2Credentials
from google.appengine.ext import db
from google.appengine.ext.webapp import template
import webapp2
from webutil import handlers as webutil_handlers


assert (appengine_config.GOOGLE_CLIENT_ID and
        appengine_config.GOOGLE_CLIENT_SECRET), (
        "Please fill in the google_client_id and google_client_secret files in "
        "your app's root directory.")

# service names and versions:
# https://developers.google.com/api-client-library/python/apis/
json_service = discovery.build('plus', 'v1')

# global. initialized in StartHandler.to_path().
oauth_decorator = None


class GooglePlusAuth(models.BaseAuth):
  """An authenticated Google+ user or page.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to the Google+ API. Stores OAuth credentials in the
  datastore. See models.BaseAuth for usage details.

  Google+-specific details: implements http() and api() but not urlopen(). api()
  returns a apiclient.discovery.Resource. The datastore entity key name is the
  Google+ user id.
  """
  user_json = db.TextProperty(required=True)
  creds_json = db.TextProperty(required=True)

  def site_name(self):
    return 'Google+'

  def user_display_name(self):
    """Returns the user's name.
    """
    return json.loads(self.user_json)['displayName']

  def creds(self):
    """Returns an oauth2client.OAuth2Credentials.
    """
    return OAuth2Credentials.from_json(self.creds_json)

  def http(self):
    """Returns an httplib2.Http that adds OAuth credentials to requests.
    """
    http = httplib2.Http()
    self.creds().authorize(http)
    return http

  def api(self):
    """Returns an apiclient.discovery.Resource for the Google+ JSON API.

    To use it, first choose a resource type (e.g. People), then make a call,
    then execute that call with an authorized Http instance. For example:

    gpa = GooglePlusAuth.get_by_key_name(123)
    results_json = gpa.people().search(query='ryan').execute(gpa.http())

    More details: https://developers.google.com/api-client-library/python/
    """
    return json_service


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

  @classmethod
  def to(cls, to_path):
    """Override this since we need to_path to instantiate the oauth decorator.
    """
    global oauth_decorator
    if oauth_decorator is None:
      oauth_decorator = OAuth2Decorator(
        client_id=appengine_config.GOOGLE_CLIENT_ID,
        client_secret=appengine_config.GOOGLE_CLIENT_SECRET,
        # G+ scopes: https://developers.google.com/+/api/oauth#oauth-scopes
        scope='https://www.googleapis.com/auth/plus.me',
        callback_path=to_path)

    class Handler(cls):
      @oauth_decorator.oauth_required
      def get(self):
        # get the current user
        user = json_service.people().get(userId='me').execute(oauth_decorator.http())
        logging.debug('Got one person: %r', user)
        creds_json = oauth_decorator.credentials.to_json()

        auth = GooglePlusAuth(key_name=user['id'],
                              creds_json=creds_json,
                              user_json=json.dumps(user))
        auth.save()
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
