"""Dropbox OAuth drop-in.

Standard OAuth 2.0 flow. Docs:
https://www.dropbox.com/developers/documentation/http/overview
https://www.dropbox.com/developers/documentation/http/documentation#authorization
"""
import logging
import urllib.parse, urllib.request

from flask import request
from google.cloud import ndb

from . import views, models
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

DROPBOX_APP_KEY = util.read('dropbox_app_key')
DROPBOX_APP_SECRET = util.read('dropbox_app_secret')
GET_AUTH_CODE_URL = '&'.join((
  'https://www.dropbox.com/1/oauth2/authorize?'
  'response_type=code',
  'client_id=%(client_id)s',
  'redirect_uri=%(redirect_uri)s',
  'state=%(state)s',
))
GET_ACCESS_TOKEN_URL = '&'.join((
  'https://api.dropbox.com/1/oauth2/token?',
  'grant_type=authorization_code',
  'code=%(code)s',
  'client_id=%(client_id)s',
  'client_secret=%(client_secret)s',
  'redirect_uri=%(redirect_uri)s',
))


class DropboxAuth(models.BaseAuth):
  """An authenticated Dropbox user or page.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to Dropbox's HTTP-based APIs. Stores OAuth credentials
  in the datastore. See models.BaseAuth for usage details.

  Implements urlopen() but not api().
  """
  access_token_str = ndb.StringProperty(required=True)

  def site_name(self):
    return 'Dropbox'

  def user_display_name(self):
    """Returns the Dropbox user id.
    """
    return self.key_id()

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def urlopen(self, url, **kwargs):
    """Wraps urlopen() and adds OAuth credentials to the request.
    """
    headers = {'Authorization': f'Bearer {self.access_token_str}'}
    try:
      return util.urlopen(urllib.request.Request(url, headers=headers), **kwargs)
    except BaseException as e:
      util.interpret_http_exception(e)
      raise


class DropboxCsrf(ndb.Model):
  """Stores a CSRF token for the Dropbox OAuth2 flow."""
  token = ndb.StringProperty(required=False)
  state = ndb.TextProperty(required=False)


class Start(views.Start):
  """Starts Dropbox auth. Requests an auth code and expects a redirect back.
  """
  NAME = 'dropbox'
  LABEL = 'Dropbox'

  def redirect_url(self, state=None):
    assert DROPBOX_APP_KEY and DROPBOX_APP_SECRET, (
      "Please fill in the dropbox_app_key and dropbox_app_secret files in "
      "your app's root directory.")

    csrf_key = DropboxCsrf(state=state).put()
    return GET_AUTH_CODE_URL % {
      'client_id': DROPBOX_APP_KEY,
      'redirect_uri': urllib.parse.quote_plus(self.to_url(state=state)),
      'state': f'{state}|{csrf_key.id()}',
    }

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args, input_style='background-color: #EEEEEE; padding: 10px', **kwargs)


class Callback(views.Callback):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """
  def dispatch_request(self):
    state = request.values['state']

    # handle errors
    error = request.values.get('error')
    error_reason = urllib.parse.unquote_plus(request.values.get('error_reason', ''))

    if error or error_reason:
      if error == 'access_denied':
        logger.info(f'User declined: {error_reason}')
        return self.finish(None, state=state)
      else:
        flask_util.error(' '.join((error, error_reason)))

    # lookup the CSRF token
    try:
      csrf_id = int(urllib.parse.unquote_plus(state).split('|')[-1])
    except (ValueError, TypeError):
      flask_util.error(f'Invalid state value {state!r}')

    csrf = DropboxCsrf.get_by_id(csrf_id)
    if not csrf:
      flask_util.error(f'No CSRF token for id {csrf_id}')

    # request an access token
    data = {
      'client_id': DROPBOX_APP_KEY,
      'client_secret': DROPBOX_APP_SECRET,
      'code': request.values['code'],
      'redirect_uri': request.base_url,
    }
    try:
      resp = util.urlopen(GET_ACCESS_TOKEN_URL % data, data=b'').read()
    except BaseException as e:
      util.interpret_http_exception(e)
      raise

    try:
      data = json_loads(resp)
    except (ValueError, TypeError):
      logger.error(f'Bad response:\n{resp}', exc_info=True)
      flask_util.error('Bad Dropbox response to access token request')

    logger.info(f"Storing new Dropbox account: {data['uid']}")
    auth = DropboxAuth(id=data['uid'], access_token_str=data['access_token'])
    auth.put()
    return self.finish(auth, state=csrf.state)
