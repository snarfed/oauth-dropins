"""Patreon OAuth 2 drop-in.

https://docs.patreon.com/#oauth
"""
from enum import Enum
import logging

from flask import request
from google.cloud import ndb
import requests
from requests_oauth2client import BearerToken, OAuth2Client
from webutil import flask_util, util
from webutil.util import json_dumps, json_loads

from . import models, views

logger = logging.getLogger(__name__)

CLIENT_ID = util.read('patreon_client_id')
CLIENT_SECRET = util.read('patreon_client_secret')

AUTH_CODE_URL = 'https://www.patreon.com/oauth2/authorize'
ACCESS_TOKEN_URL = 'https://www.patreon.com/api/oauth2/token'
API_IDENTITY_URL = 'https://www.patreon.com/api/oauth2/v2/identity?include=memberships&fields%5Buser%5D=full_name,image_url,thumb_url,url,vanity&fields%5Bmember%5D=patron_status,currently_entitled_amount_cents,pledge_cadence,last_charge_date,last_charge_status,next_charge_date,is_free_trial,is_gifted'

# https://docs.patreon.com/#scopes
ALL_SCOPES = (
  'campaigns',
  'campaigns.lives',
  'campaigns.members',
  'campaigns.members.address',
  'campaigns.members[email]',
  'campaigns.posts',
  'identity',
  'identity.memberships',
  'identity[email]',
  'w:campaigns.lives',
  'w:campaigns.webhook',
)


class Membership(str, Enum):
  """A user's membership in the OAuth client's campaign."""
  PAID = 'paid'
  FREE = 'free'
  FORMER = 'former'


class PatreonAuth(models.BaseAuth):
  """An OAuth-authenticated Patreon user.

  Provides methods that return information about this user and store OAuth 2 tokens
  in the datastore. See models.BaseAuth for usage details.

  The datastore entity key name is the Patreon user id.
  """
  # Fields: access_token, refresh_token, expires_in, scope, token_type
  token_json = ndb.TextProperty(required=True)
  # JSON:API identity response, with user attributes in data.attributes
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Patreon'

  def user_display_name(self):
    """Returns the user's full name."""
    return json_loads(self.user_json)['data']['attributes'].get('full_name')

  def image_url(self):
    """Returns the user's profile picture URL, if any."""
    return json_loads(self.user_json)['data']['attributes'].get('image_url')

  def user_url(self):
    """Returns the user's Patreon profile URL, if any."""
    return json_loads(self.user_json)['data']['attributes'].get('url')

  def get_membership(self):
    """Returns the user's membership in the OAuth client's campaign, if any.

    Returns:
      Membership: or None if they've never been a member
    """
    for included in json_loads(self.user_json).get('included', []):
      if included.get('type') != 'member':
        continue

      attrs = included.get('attributes') or {}
      status = attrs.get('patron_status')
      if status == 'active_patron':
        return (Membership.PAID if attrs.get('currently_entitled_amount_cents')
                else Membership.FREE)
      elif status in ('declined_patron', 'former_patron'):
        return Membership.FORMER

  def access_token(self):
    """Returns the OAuth access token string."""
    return json_loads(self.token_json)['access_token']

  @property
  def refresh_token(self):
    """Returns the refresh token, if any."""
    return json_loads(self.token_json).get('refresh_token')

  def session(self):
    """Returns a :class:`requests.Session` that uses this user's access token."""
    session = requests.Session()
    session.auth = BearerToken(self.access_token())
    return session


class Start(views.Start):
  """Starts three-legged OAuth with Patreon.

  Redirects to Patreon's auth prompt for user approval.
  """
  NAME = 'patreon'
  LABEL = 'Patreon'
  SCOPE_SEPARATOR = ' '
  DEFAULT_SCOPE = 'identity'

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args, input_style='background-color: #EEEEEE; padding: 10px', **kwargs)

  def redirect_url(self, state=None):
    assert CLIENT_ID and CLIENT_SECRET, \
      "Please fill in the patreon_client_id and patreon_client_secret files in your app's root directory."

    client = OAuth2Client(token_endpoint=ACCESS_TOKEN_URL,
                          authorization_endpoint=AUTH_CODE_URL,
                          client_id=CLIENT_ID,
                          redirect_uri=self.to_url(),
                          code_challenge_method=None,
                          session=util.session)
    auth_url = client.authorization_request(
      scope=self.scope, state=state, nonce=None).uri
    logger.info(f'Redirecting to {auth_url}')
    return auth_url


class Callback(views.Callback):
  """The OAuth callback. Fetches an access token and redirects to the front page.
  """
  def dispatch_request(self):
    state = request.values.get('state')
    error = request.values.get('error')
    desc = request.values.get('error_description')
    if error:
      msg = f'Error: {error}: {desc}'
      logger.info(msg)
      if error == 'access_denied':
        return self.finish(None, state=state)
      else:
        flask_util.error(msg)

    client = OAuth2Client(token_endpoint=ACCESS_TOKEN_URL, client_id=CLIENT_ID,
                          client_secret=CLIENT_SECRET, session=util.session)
    token = client.authorization_code(request.values['code'],
                                      redirect_uri=request.base_url)
    logger.info(f'Got access token with scope {token.scope}')

    resp = util.requests_get(API_IDENTITY_URL, auth=token)
    resp.raise_for_status()
    user_json = resp.json()
    logger.info(f'Got user {user_json}')

    auth = PatreonAuth(id=user_json['data']['id'],
                       token_json=json_dumps(token.as_dict()),
                       user_json=json_dumps(user_json))
    auth.put()

    return self.finish(auth, state=state)
