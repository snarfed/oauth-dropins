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


def discover_authorization_endpoint(me, resp=None):
  found = discover_endpoint(me, 'authorization_endpoint', resp)
  if found == "":
    return INDIEAUTH_URL
  return found

def discover_token_endpoint(me, resp=None):
  return discover_endpoint(me, 'token_endpoint', resp)

def discover_endpoint(me, rel_link, resp=None):
  """Fetch a URL and look for the `rel_link` Link header or
  rel-value.

  Args:
    me: string, URL to fetch
    resp: :class:`requests.Response` (optional), re-use response if it's already
      been fetched

  Return:
    string, the discovered `rel_link` or an empty string
  """
  try:
    resp = resp or util.requests_get(me)
  except (ValueError, requests.URLRequired, requests.TooManyRedirects) as e:
    flask_util.error(str(e))

  if resp.status_code // 100 != 2:
    logger.warning(
      'could not fetch user url "%s". got response code: %d',
      me, resp.status_code)
    return ""
  # check endpoint header first
  endpoint = resp.links.get(rel_link, {}).get('url')
  if endpoint:
    return endpoint
  # check the html content
  soup = util.parse_html(resp.text)
  link = soup.find('link', {'rel': rel_link})
  endpoint = link and link.get('href')
  if endpoint:
    return endpoint
  return ""

def build_user_json(me, resp=None):
  """user_json contains an h-card, rel-me links, and "me"

  Args:
    me: string, URL of the user, returned by
    resp: :class:`requests.Response` (optional), re-use response if it's already
      been fetched

  Return:
    dict, with 'me', the URL for this person; 'h-card', the representative h-card
      for this page; 'rel-me', a list of rel-me URLs found at this page
  """
  user_json = {'me': me}

  resp = resp or util.requests_get(me)
  if resp.status_code // 100 != 2:
    logger.warning(
      'could not fetch user url "%s". got response code: %d',
      me, resp.status_code)
    return user_json

  mf2 = util.parse_mf2(resp, resp.url)
  user_json['rel-me'] = mf2['rels'].get('me')
  user_json['h-card'] = mf2util.representative_hcard(mf2, me)
  logger.debug(f'built user-json {user_json!r}')
  return util.trim_nulls(user_json)


class IndieAuth(models.BaseAuth):
  """An authenticated IndieAuth user.

  Provides methods that return information about this user. Stores credentials
  in the datastore. Key is the domain name. See models.BaseAuth for usage
  details.
  """
  user_json = ndb.TextProperty(required=True)  # generally this has only 'me'

  def site_name(self):
    return 'IndieAuth'

  def user_display_name(self):
    """Returns the user's domain."""
    return self.key_id()

  def access_token(self):
    """Return the access token, N/A for IndieAuth"""
    return None


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

    redirect_uri = self.to_url()
    endpoint = discover_authorization_endpoint(me)
    token_endpoint = discover_token_endpoint(me)
    url = ""
    if token_endpoint:
      code_verifier, code_challenge = pkce.generate_pkce_pair()

      url = endpoint + '?' + urllib.parse.urlencode({
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
      endpoint = discover_authorization_endpoint(me)

      url = endpoint + '?' + urllib.parse.urlencode({
        'me': me,
        'client_id': INDIEAUTH_CLIENT_ID,
        'redirect_uri': redirect_uri,
        'state': util.encode_oauth_state({
          'endpoint': endpoint,
          'me': me,
          'state': state,
          }),
        })

    logger.info(f'Redirecting to IndieAuth: {url}')
    return url

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

    if validate_resp.status_code // 100 == 2:
      data = util.sniff_json_or_form_encoded(validate_resp.text)
      if data.get('me'):
        verified = data.get('me')
        user_json = build_user_json(verified)
        indie_auth = IndieAuth(id=verified, user_json=json_dumps(user_json))
        indie_auth.put()
        return self.finish(indie_auth, state=state)
      else:
        flask_util.error('Verification response missing required "me" field')
    else:
      flask_util.error(f'IndieAuth verification failed: {validate_resp.status_code} {validate_resp.text}')
