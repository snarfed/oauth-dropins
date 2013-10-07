"""Google+ OAuth drop-in.
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
from oauth2client.appengine import CredentialsModel
from oauth2client.appengine import OAuth2Decorator
from oauth2client.appengine import StorageByKeyName
from google.appengine.ext import db
from google.appengine.ext.webapp import template
import webapp2


# service names and versions:
# https://developers.google.com/api-client-library/python/reference/supported_apis
json_service = discovery.build('plus', 'v1')
oauth = OAuth2Decorator(
  client_id=appengine_config.GOOGLE_CLIENT_ID,
  client_secret=appengine_config.GOOGLE_CLIENT_SECRET,
  # G+ scopes: https://developers.google.com/+/api/oauth#oauth-scopes
  scope='https://www.googleapis.com/auth/plus.me',
  callback_path='/googleplus/oauth2callback')


# TODO: port to models.Site
class GooglePlusAuth(db.Model):
  """A Google+ account. The key name is the Google+ user id."""
  info_json = db.TextProperty(required=True)
  creds_json = db.TextProperty(required=True)


class StartHandler(webapp2.RequestHandler):
  """Adds a Google+ account. Authenticates via OAuth if necessary."""

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
    GooglePlusAuth.get_or_insert(key_name=user['id'], creds_json=creds_json,
                                 info_json=json.dumps(user))

    # redirect so that refreshing doesn't rewrite this GooglePlus entity
    self.redirect('/?%s' % urllib.urlencode(
        {'googleplus_name': user['displayName'],
         'googleplus_credentials': creds_json,
         }))


application = webapp2.WSGIApplication([
    ('/googleplus/start', StartHandler),
    (oauth.callback_path, oauth.callback_handler()),
    ], debug=appengine_config.DEBUG)
