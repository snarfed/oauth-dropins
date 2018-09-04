"""Dropbox OAuth drop-in.

Standard OAuth 2.0 flow. Docs:
https://www.dropbox.com/developers/core/docs
https://www.dropbox.com/developers/reference/oauthguide
"""

import json
import logging
import urllib
import urllib2

import appengine_config

from google.appengine.ext import ndb
from webob import exc
from webutil import util

import handlers
import models


# the str() is since WSGI middleware chokes on unicode redirect URLs :/
GET_AUTH_CODE_URL = str('&'.join((
  'https://www.dropbox.com/1/oauth2/authorize?'
  'response_type=code',
  'client_id=%(client_id)s',
  'redirect_uri=%(redirect_uri)s',
  'state=%(state)s',
)))

GET_ACCESS_TOKEN_URL = str('&'.join((
  'https://api.dropbox.com/1/oauth2/token?',
  'grant_type=authorization_code',
  'code=%(code)s',
  'client_id=%(client_id)s',
  'client_secret=%(client_secret)s',
  'redirect_uri=%(redirect_uri)s',
)))


class DropboxAuth(models.BaseAuth):
  """An authenticated Dropbox user or page.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to Dropbox's HTTP-based APIs. Stores OAuth credentials
  in the datastore. See models.BaseAuth for usage details.

  Implements urlopen() but not http() or api().
  """
  access_token_str = ndb.StringProperty(required=True)

  def site_name(self):
    return 'Dropbox'

  def user_display_name(self):
    """Returns the Dropbox user id.
    """
    return self.key.string_id()

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds OAuth credentials to the request.
    """
    headers = {'Authorization': 'Bearer %s' % self.access_token_str}
    try:
      return util.urlopen(urllib2.Request(url, headers=headers), **kwargs)
    except BaseException, e:
      util.interpret_http_exception(e)
      raise


class DropboxCsrf(ndb.Model):
  """Stores a CSRF token for the Dropbox OAuth2 flow."""
  token = ndb.StringProperty(required=False)
  state = ndb.TextProperty(required=False)


class StartHandler(handlers.StartHandler):
  """Starts Dropbox auth. Requests an auth code and expects a redirect back.
  """
  def redirect_url(self, state=None):
    assert (appengine_config.DROPBOX_APP_KEY and
            appengine_config.DROPBOX_APP_SECRET), (
      "Please fill in the dropbox_app_key and dropbox_app_secret files in "
      "your app's root directory.")

    csrf_key = DropboxCsrf(state=state).put()
    return GET_AUTH_CODE_URL % {
      'client_id': appengine_config.DROPBOX_APP_KEY,
      'redirect_uri': urllib.quote_plus(self.to_url(state=state)),
      'state': '%s|%s' % (state, csrf_key.id()),
    }


class CallbackHandler(handlers.CallbackHandler):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """
  def get(self):
    state = util.get_required_param(self, 'state')

    # handle errors
    error = self.request.get('error')
    error_reason = urllib.unquote_plus(self.request.get('error_reason', ''))

    if error or error_reason:
      if error == 'access_denied':
        logging.info('User declined: %s', error_reason)
        self.finish(None, state=state)
        return
      else:
        raise exc.HTTPBadRequest(' '.join((error, error_reason)))

    # lookup the CSRF token
    try:
      csrf_id = int(urllib.unquote_plus(state).split('|')[-1])
    except (ValueError, TypeError):
      raise exc.HTTPBadRequest('Invalid state value %r' % state)

    csrf = DropboxCsrf.get_by_id(csrf_id)
    if not csrf:
      raise exc.HTTPBadRequest('No CSRF token for id %s' % csrf_id)

    # request an access token
    data = {
      'client_id': appengine_config.DROPBOX_APP_KEY,
      'client_secret': appengine_config.DROPBOX_APP_SECRET,
      'code': util.get_required_param(self, 'code'),
      'redirect_uri': self.request.path_url,
    }
    try:
      resp = util.urlopen(GET_ACCESS_TOKEN_URL % data, data='').read()
    except BaseException, e:
      util.interpret_http_exception(e)
      raise

    try:
      data = json.loads(resp)
    except (ValueError, TypeError):
      logging.exception('Bad response:\n%s', resp)
      raise exc.HttpBadRequest('Bad Dropbox response to access token request')


    logging.info('Storing new Dropbox account: %s', data['uid'])
    auth = DropboxAuth(id=data['uid'], access_token_str=data['access_token'])
    auth.put()
    self.finish(auth, state=csrf.state)
