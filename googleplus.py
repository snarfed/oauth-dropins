"""Google+ OAuth drop-in.

Google+ API docs: https://developers.google.com/+/api/latest/
Python API client docs: https://developers.google.com/api-client-library/python/
"""

import json
import httplib2
import logging
import urllib

import appengine_config
import models

from webutil import handlers
from webutil import util

from apiclient import discovery
from apiclient.errors import HttpError
from oauth2client.appengine import CredentialsModel, OAuth2Decorator, StorageByKeyName
from oauth2client.client import Credentials, OAuth2Credentials
from google.appengine.ext import db
from google.appengine.ext.webapp import template
import webapp2


# service names and versions:
# https://developers.google.com/api-client-library/python/apis/
json_service = discovery.build('plus', 'v1')
oauth = OAuth2Decorator(
  client_id=appengine_config.GOOGLE_CLIENT_ID,
  client_secret=appengine_config.GOOGLE_CLIENT_SECRET,
  # G+ scopes: https://developers.google.com/+/api/oauth#oauth-scopes
  scope='https://www.googleapis.com/auth/plus.me',
  callback_path='/googleplus/oauth2callback')


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
    return json.loads(user_json)['displayName']

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


class StartHandler(webapp2.RequestHandler):
  """Finishes Facebook auth. (The oauth decorator handles OAuth redirects.)
  """
  def handle_exception(self, e, debug):
    """Exception handler that passes back HttpErrors as real HTTP errors.
    """
    if isinstance(e, HttpError):
      logging.exception(e)
      self.response.set_status(e.resp.status)
      self.response.write(str(e))
    else:
      return handlers.handle_exception(self, e, debug)

  @oauth.oauth_required
  def get(self):
    # get the current user
    user = json_service.people().get(userId='me').execute(oauth.http())
    logging.debug('Got one person: %r', user)
    creds_json = oauth.credentials.to_json()
    GooglePlusAuth.get_or_insert(key_name=user['id'],
                                 creds_json=creds_json,
                                 user_json=json.dumps(user))

    # redirect so that refreshing doesn't rewrite this GooglePlus entity
    self.redirect('/?%s' % urllib.urlencode(
        {'googleplus_name': user['displayName'],
         'googleplus_credentials': creds_json,
         }))


application = webapp2.WSGIApplication([
    ('/googleplus/start', StartHandler),
    (oauth.callback_path, oauth.callback_handler()),
    ], debug=appengine_config.DEBUG)
