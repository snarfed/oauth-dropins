"""Instagram OAuth drop-in.

Instagram API docs: http://instagram.com/developer/endpoints/

Almost identical to Facebook, except the access token request has `code`
and `grant_type` query parameters instead of just `auth_code`, the response
has a `user` object instead of `id`, and the call to GET_ACCESS_TOKEN_URL
is a POST instead of a GET.
TODO: unify them.
"""
import logging
import os
import urllib.parse

from flask import abort, request
from google.cloud import ndb

from . import facebook, views, models
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

INSTAGRAM_CLIENT_ID = util.read('instagram_client_id')
INSTAGRAM_CLIENT_SECRET = util.read('instagram_client_secret')
INSTAGRAM_SESSIONID_COOKIE = (os.getenv('INSTAGRAM_SESSIONID_COOKIE') or
                              util.read('instagram_sessionid_cookie'))
# instagram api url templates. can't (easily) use urlencode() because i want to
# keep the %(...)s placeholders as is and fill them in later in code.
GET_AUTH_CODE_URL = '&'.join((
    'https://api.instagram.com/oauth/authorize?',
    'client_id=%(client_id)s',
    'scope=%(scope)s',
    # redirect_uri here must be the same in the access token request!
    'redirect_uri=%(redirect_uri)s',
    'response_type=code',
))
GET_ACCESS_TOKEN_URL = 'https://api.instagram.com/oauth/access_token'


class InstagramAuth(models.BaseAuth):
  """An authenticated Instagram user or page.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to Instagram's HTTP-based APIs. Stores OAuth credentials
  in the datastore. See models.BaseAuth for usage details.

  Instagram-specific details: implements urlopen() but not api(). The key name
  is the Instagram username.
  """
  auth_code = ndb.StringProperty(required=True)
  access_token_str = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Instagram'

  def user_display_name(self):
    """Returns the Instagram username.
    """
    return self.key_id()

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def urlopen(self, url, **kwargs):
    """Wraps urlopen() and adds OAuth credentials to the request.
    """
    return models.BaseAuth.urlopen_access_token(url, self.access_token_str,
                                                **kwargs)


class Start(views.Start):
  """Starts Instagram auth. Requests an auth code and expects a redirect back.
  """
  NAME = 'instagram'
  LABEL = 'Instagram'
  DEFAULT_SCOPE = 'basic'

  def redirect_url(self, state=None):
    assert INSTAGRAM_CLIENT_ID and INSTAGRAM_CLIENT_SECRET, (
      "Please fill in the instagram_client_id and instagram_client_secret "
      "files in your app's root directory.")
    # http://instagram.com/developer/authentication/
    return GET_AUTH_CODE_URL % {
      'client_id': INSTAGRAM_CLIENT_ID,
      # instagram uses + instead of , to separate scopes
      # http://instagram.com/developer/authentication/#scope
      'scope': self.scope.replace(',', '+'),
      # TODO: CSRF protection identifier.
      'redirect_uri': urllib.parse.quote_plus(self.to_url(state=state)),
    }

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args,
      input_style='background-color: #EEEEEE; padding: 5px; padding-top: 8px; padding-bottom: 2px',
      **kwargs)


class Callback(views.Callback):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """
  def dispatch_request(self):
    err = facebook.Callback.handle_error(self)
    if err:
      return err

    # http://instagram.com/developer/authentication/
    auth_code = request.values['code']
    data = {
      'client_id': INSTAGRAM_CLIENT_ID,
      'client_secret': INSTAGRAM_CLIENT_SECRET,
      'code': auth_code,
      'redirect_uri': self.request_url_with_state(),
      'grant_type': 'authorization_code',
    }

    try:
      resp = util.requests_post(GET_ACCESS_TOKEN_URL, data=data)
      resp.raise_for_status()
    except BaseException as e:
      util.interpret_http_exception(e)
      raise

    try:
      data = json_loads(resp.text)
    except (ValueError, TypeError):
      logger.error(f'Bad response:\n{resp}', exc_info=True)
      flask_util.error('Bad Instagram response to access token request')

    if 'error_type' in resp:
      abort(502, f"{resp['error_type']} {data.get('code')} {data.get('error_message')}")

    access_token = data['access_token']
    username = data['user']['username']

    auth = InstagramAuth(id=username,
                         auth_code=auth_code,
                         access_token_str=access_token,
                         user_json=json_dumps(data['user']))
    auth.put()
    return self.finish(auth, state=request.values.get('state'))
