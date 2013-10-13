"""Dropbox OAuth drop-in.

Dropbox API docs:
https://www.dropbox.com/developers/core/start/python
https://www.dropbox.com/static/developers/dropbox-python-sdk-1.6-docs/
https://www.dropbox.com/developers/core/docs
"""

import json
import logging
import urllib

import appengine_config
from python_dropbox.client import DropboxOAuth2Flow, DropboxClient
import models
from webob import exc
from webutil import handlers
from webutil import util

from google.appengine.ext import db
import models
import webapp2


OAUTH_CALLBACK = '%s/dropbox/oauth_callback'
CSRF_PARAM = 'dropbox-auth-csrf-token'


class DropboxAuth(models.BaseAuth):
  """An authenticated Dropbox user or page.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to Dropbox's HTTP-based APIs. Stores OAuth credentials
  in the datastore. See models.BaseAuth for usage details.

  Dropbox-specific details: implements urlopen() and api() but not http(). api()
  returns a python_dropbox.DropboxClient. The key name is the Dropbox user id.
  """
  access_token = db.StringProperty(required=True)

  def site_name(self):
    return 'Dropbox'

  def user_display_name(self):
    """Returns the Dropbox user id.
    """
    return self.key().name()

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds OAuth credentials to the request.
    """
    return BaseAuth.urlopen_access_token(url, self.access_token, **kwargs)

  def api(self):
    """Returns a python_dropbox.DropboxClient.

    Details: https://www.dropbox.com/static/developers/dropbox-python-sdk-1.6-docs/
    """
    return DropboxClient(self.access_token)


class DropboxCsrf(db.Model):
  """Stores a CSRF token for the Dropbox OAuth2 flow."""
  token = db.StringProperty(required=False)


def handle_exception(self, e, debug):
  """Exception handler that handles Dropbox client errors.
  """
  if isinstance(e, (DropboxOAuth2Flow.CsrfException,
                      DropboxOAuth2Flow.ProviderException)):
    logging.exception()
    raise exc.HTTPForbidden()
  elif isinstance(e, (DropboxOAuth2Flow.BadRequestException,
                      DropboxOAuth2Flow.BadStateException,
                      DropboxOAuth2Flow.NotApprovedException)):
    logging.exception()
    raise exc.HTTPBadRequest()
  else:
    return handlers.handle_exception(self, e, debug)


class StartHandler(webapp2.RequestHandler):
  """Starts Dropbox auth. Requests an auth code and expects a redirect back.
  """
  handle_exception = handle_exception

  def post(self):
    csrf = DropboxCsrf()
    csrf.save()
    csrf_holder = {}
    flow = DropboxOAuth2Flow(appengine_config.DROPBOX_APP_KEY,
                             appengine_config.DROPBOX_APP_SECRET,
                             OAUTH_CALLBACK % self.request.host_url,
                             csrf_holder, CSRF_PARAM)

    auth_url = flow.start(url_state=str(csrf.key().id()))

    csrf.token = csrf_holder[CSRF_PARAM]
    csrf.save()
    logging.info('Stored DropboxCsrf id %d, redirecting to Dropbox: %s',
      csrf.key().id(), auth_url)
    self.redirect(auth_url)


class CallbackHandler(webapp2.RequestHandler):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """
  handle_exception = handle_exception

  def get(self):
    # lookup the CSRF token
    csrf_id = self.request.get('state').split('|')[1]
    csrf = DropboxCsrf.get_by_id(int(csrf_id))
    if not csrf:
      raise exc.HTTPBadRequest('No CSRF token for id %s', csrf_id)

    # extract the OAuth access token
    csrf_holder = {CSRF_PARAM: csrf.token}
    flow = DropboxOAuth2Flow(appengine_config.DROPBOX_APP_KEY,
                             appengine_config.DROPBOX_APP_SECRET,
                             OAUTH_CALLBACK % self.request.host_url,
                             csrf_holder, CSRF_PARAM)
    access_token, user_id, state = flow.finish(self.request.params)

    logging.info('Storing new Dropbox account: %s', user_id)
    dropbox = DropboxAuth.get_or_insert(key_name=user_id,
                                        access_token=access_token)

    # redirect so that refreshing the page doesn't try to regenerate the oauth
    # token, which won't work.
    self.redirect('/?%s' % urllib.urlencode(
        {'dropbox_id': user_id,
         'dropbox_access_token': util.ellipsize(access_token),
         }))


application = webapp2.WSGIApplication([
    ('/dropbox/start', StartHandler),
    ('/dropbox/oauth_callback', CallbackHandler),
    ], debug=appengine_config.DEBUG)
