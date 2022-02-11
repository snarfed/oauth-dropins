"""LinkedIn OAuth drop-in.

API docs:
https://www.linkedin.com/developers/
https://docs.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin
"""
import logging
import urllib.parse

from flask import request
from google.cloud import ndb

from . import views
from .models import BaseAuth
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

LINKEDIN_CLIENT_ID = util.read('linkedin_client_id')
LINKEDIN_CLIENT_SECRET = util.read('linkedin_client_secret')
# URL templates. Can't (easily) use urlencode() because I want to keep
# the %(...)s placeholders as is and fill them in later in code.
AUTH_CODE_URL = '&'.join((
  'https://www.linkedin.com/oauth/v2/authorization?'
  'response_type=code',
  'client_id=%(client_id)s',
  # https://docs.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api?context=linkedin/consumer/context#permissions
  'scope=%(scope)s',
  # must be the same in the access token request
  'redirect_uri=%(redirect_uri)s',
  'state=%(state)s',
))
ACCESS_TOKEN_URL = 'https://www.linkedin.com/oauth/v2/accessToken'
API_PROFILE_URL = 'https://api.linkedin.com/v2/me'


class LinkedInAuth(BaseAuth):
  """An authenticated LinkedIn user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the LinkedIn REST API. Stores OAuth credentials in the datastore.
  See models.BaseAuth for usage details.

  Implements get() but not urlopen() or api(). The key name is the ID (a URN).

  Note that LI access tokens can be over 500 chars (up to 1k!), so they need to
  be TextProperty instead of StringProperty.
  https://docs.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow?context=linkedin/consumer/context#access-token-response
  """
  access_token_str = ndb.TextProperty(required=True)
  user_json = ndb.TextProperty()

  def site_name(self):
    return 'LinkedIn'

  def user_display_name(self):
    """Returns the user's first and last name.
    """
    def name(field):
      user = json_loads(self.user_json)
      loc = user.get(field, {}).get('localized', {})
      if loc:
          return loc.get('en_US') or loc.values()[0]
      return ''

    return f"{name('firstName')} {name('lastName')}"

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def get(self, *args, **kwargs):
    """Wraps requests.get() and adds the Bearer token header.

    TODO: unify with github.py, medium.py.
    """
    return self._requests_call(util.requests_get, *args, **kwargs)

  def post(self, *args, **kwargs):
    """Wraps requests.post() and adds the Bearer token header.

    TODO: unify with github.py, medium.py.
    """
    return self._requests_call(util.requests_post, *args, **kwargs)

  def _requests_call(self, fn, *args, **kwargs):
    headers = kwargs.setdefault('headers', {})
    headers['Authorization'] = 'Bearer ' + self.access_token_str

    resp = fn(*args, **kwargs)

    try:
      resp.raise_for_status()
    except BaseException as e:
      util.interpret_http_exception(e)
      raise
    return resp


class Start(views.Start):
  """Starts LinkedIn auth. Requests an auth code and expects a redirect back.
  """
  NAME = 'linkedin'
  LABEL = 'LinkedIn'
  DEFAULT_SCOPE = 'r_liteprofile'

  def redirect_url(self, state=None):
    # assert state, 'LinkedIn OAuth 2 requires state parameter'
    assert LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET, \
      "Please fill in the linkedin_client_id and linkedin_client_secret files in your app's root directory."
    return AUTH_CODE_URL % {
      'client_id': LINKEDIN_CLIENT_ID,
      'redirect_uri': urllib.parse.quote_plus(self.to_url()),
      'state': urllib.parse.quote_plus(state or ''),
      'scope': self.scope,
    }

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args,
      input_style='background-color: #EEEEEE; padding: 5px; padding-top: 8px; padding-bottom: 2px',
      **kwargs)


class Callback(views.Callback):
  """The OAuth callback. Fetches an access token and stores it.
  """
  def dispatch_request(self):
    # handle errors
    error = request.values.get('error')
    desc = request.values.get('error_description')
    if error:
      # https://docs.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow?context=linkedin/consumer/context#application-is-rejected
      if error in ('user_cancelled_login', 'user_cancelled_authorize'):
        logger.info(f"User declined: {request.values.get('error_description')}")
        return self.finish(None, state=request.values.get('state'))
      else:
        flask_util.error(f'{error} {desc}')

    # extract auth code and request access token
    auth_code = request.values['code']
    data = {
      'grant_type': 'authorization_code',
      'code': auth_code,
      'client_id': LINKEDIN_CLIENT_ID,
      'client_secret': LINKEDIN_CLIENT_SECRET,
      # redirect_uri here must be the same in the oauth code request!
      # (the value here doesn't actually matter since it's requested server side.)
      'redirect_uri': request.base_url,
    }

    resp = util.requests_post(ACCESS_TOKEN_URL, data=data)
    resp.raise_for_status()
    resp = json_loads(resp.text)

    logger.debug(f'Access token response: {resp}')
    if resp.get('serviceErrorCode'):
      flask_util.error(resp)

    access_token = resp['access_token']
    resp = LinkedInAuth(access_token_str=access_token).get(API_PROFILE_URL).json()
    logger.debug(f'Profile response: {resp}')
    auth = LinkedInAuth(id=resp['id'], access_token_str=access_token,
                        user_json=json_dumps(resp))
    auth.put()

    return self.finish(auth, state=request.values.get('state'))
