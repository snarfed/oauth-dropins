"""IndieAuth drop-in.

https://indieauth.com/developers
"""
import logging
import urllib.parse

from flask import request
from google.cloud import ndb
import mf2util
import pkce
import requests

from . import models, views
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

INDIEAUTH_CLIENT_ID = util.read('indieauth_client_id')
INDIEAUTH_URL = 'https://indieauth.com/auth'


def discover_endpoint(rel, resp):
  """Fetch a URL and look for the `rel` Link header or HTML value.

  Args:
    rel: string, rel name to look for
    resp: :class:`requests.Response` to look in

  Return:
    string, the discovered `rel` value, or None if no endpoint was discovered
  """
  # check endpoint header first
  endpoint = resp.links.get(rel, {}).get('url')
  if endpoint:
    return endpoint

  # check the html content
  soup = util.parse_html(resp.text)
  link = soup.find('link', {'rel': rel})
  if link:
    return link.get('href')


def build_user_json(me):
  """Returns a JSON dict with h-card, rel-me links, and me value.

  Args:
    me: string, URL of the user, returned by
    resp: :class:`requests.Response` to use

  Return:
    dict, with 'me', the URL for this person; 'h-card', the representative h-card
      for this page; 'rel-me', a list of rel-me URLs found at this page
  """
  user_json = {'me': me}

  resp = util.requests_get(me)
  if resp.status_code // 100 != 2:
    logger.warning(f'could not fetch user url {me}, got response {resp.status_code}')
    return user_json

  mf2 = util.parse_mf2(resp, resp.url)
  user_json.update({
    'rel-me': mf2['rels'].get('me'),
    'h-card': mf2util.representative_hcard(mf2, me),
  })
  logger.debug(f'built user-json {user_json!r}')
  return util.trim_nulls(user_json)


class IndieAuth(models.BaseAuth):
  """An authenticated IndieAuth user.

  Provides methods that return information about this user. Stores credentials
  in the datastore. Key is the authed `me` URL value. See models.BaseAuth for
  usage details.
  """
  user_json = ndb.TextProperty(required=True)  # generally this has only 'me'
  access_token_str = ndb.StringProperty()
  refresh_token_str = ndb.StringProperty()

  def site_name(self):
    return 'IndieAuth'

  def user_display_name(self):
    """Returns the user's domain."""
    return self.key_id()

  def access_token(self):
    """Return the access token, N/A for IndieAuth"""
    return self.access_token_str


class Start(views.Start):
  """Starts the IndieAuth flow. Requires the 'me' parameter with the
  user URL that we want to authenticate.
  """
  NAME = 'indieauth'
  LABEL = 'IndieAuth'

  def redirect_url(self, state=None, me=None):
    assert INDIEAUTH_CLIENT_ID, (
      "Please fill in the indieauth_client_id in your app's root directory.")

    # TODO: unify with mastodon?
    if not me:
      me = request.values['me']
    parsed = urllib.parse.urlparse(me)
    if not parsed.scheme:
      me = 'http://' + me

    # fetch user URL
    redirect_uri = self.to_url()
    try:
      resp = util.requests_get(me)
    except (ValueError, requests.URLRequired, requests.TooManyRedirects) as e:
      flask_util.error(str(e))

    # discover endpoints
    if resp.ok:
      token_endpoint = discover_endpoint('token_endpoint', resp)
      auth_endpoint = (discover_endpoint('authorization_endpoint', resp) or
                       INDIEAUTH_URL)
    else:
      logger.warning(f'could not fetch user url {me}, got response {resp.status_code}')
      auth_endpoint = INDIEAUTH_URL
      token_endpoint = None

    # construct redirect URL
    if token_endpoint:
      code_verifier, code_challenge = pkce.generate_pkce_pair()
      return auth_endpoint + '?' + urllib.parse.urlencode({
        'me': me,
        'client_id': INDIEAUTH_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'scope': 'profile',
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
        'response_type': 'code',
        'state': util.encode_oauth_state({
          'code_verifier': code_verifier,
          'token_endpoint': token_endpoint,
          'me': me,
          'state': state,
          }),
        })
    else:
      return auth_endpoint + '?' + urllib.parse.urlencode({
        'me': me,
        'client_id': INDIEAUTH_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'state': util.encode_oauth_state({
          'endpoint': auth_endpoint,
          'me': me,
          'state': state,
        }),
      })

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args,
      input_style='background-color: #EBEBEB; padding: 5px',
      form_extra='<input type="url" name="me" class="form-control" placeholder="Your web site" required style="width: 150px; height: 50px; display:inline;" />',
      **kwargs)


class Callback(views.Callback):
  """The callback view from the IndieAuth request. Performs an Authorization
  Code grant to verify the code."""
  def dispatch_request(self):
    code = request.values['code']
    state = util.decode_oauth_state(request.values['state'])

    token_endpoint = state.get('token_endpoint')
    me = state.get('me')
    if token_endpoint:
      # TODO: validate that the `iss` matches the value that is retrieved from the IndieAuth Server Metadata https://indieauth.spec.indieweb.org/#indieauth-server-metadata
      code_verifier = state.get('code_verifier') or ''
      state = state.get('state') or ''
      validate_resp = util.requests_post(token_endpoint, data={
        'grant_type': 'authorization_code',
        'client_id': INDIEAUTH_CLIENT_ID,
        'code': code,
        'redirect_uri': request.base_url,
        'code_verifier': code_verifier,
      })
    else:
      endpoint = state.get('endpoint')
      me = state.get('me')
      if not endpoint or not me:
        flask_util.error("invalid state parameter")

      state = state.get('state') or ''
      validate_resp = util.requests_post(endpoint, data={
        'me': me,
        'client_id': INDIEAUTH_CLIENT_ID,
        'code': code,
        'redirect_uri': request.base_url,
        'state': state,
      })

    if validate_resp.ok:
      data = util.sniff_json_or_form_encoded(validate_resp.text)
      if data.get('me'):
        verified = data.get('me')
        user_json = build_user_json(verified)
        indie_auth = IndieAuth(id=verified,
                               user_json=json_dumps(user_json),
                               access_token_str=data.get('access_token'),
                               refresh_token_str=data.get('refresh_token'),
                               )
        indie_auth.put()
        return self.finish(indie_auth, state=state)
      else:
        flask_util.error('Verification response missing required "me" field')
    else:
      flask_util.error(f'IndieAuth verification failed: {validate_resp.status_code} {validate_resp.text}')
