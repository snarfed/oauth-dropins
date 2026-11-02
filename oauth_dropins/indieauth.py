"""IndieAuth drop-in.

https://indieauth.net/
"""
import logging
import secrets
import urllib.parse

from flask import request
from google.cloud import ndb
import mf2util
import pkce
import requests
from webutil import appengine_info, flask_util, util
from webutil.util import json_dumps, json_loads

from . import models, views

logger = logging.getLogger(__name__)

INDIELOGIN_CLIENT_ID = ('http://localhost:8080/'
                       if appengine_info.LOCAL_SERVER
                       else util.read('indielogin_client_id'))
INDIELOGIN_URL = 'https://indielogin.com/authorize'
INDIELOGIN_TOKEN_URL = 'https://indielogin.com/token'
INDIELOGIN_ISSUER = 'https://indielogin.com/'


def discover_endpoint(rel, resp):
  """Fetch a URL and look for the ``rel`` Link header or HTML value.

  Args:
    rel (str): rel name to look for
    resp (requests.Response): response to look in

  Return:
    str: discovered `rel` value, or None if no endpoint was discovered
  """
  # check endpoint header first
  endpoint = resp.links.get(rel, {}).get('url')
  if endpoint:
    return urllib.parse.urljoin(resp.url, endpoint)

  # check the html content
  soup = util.parse_html(resp.text)
  link = soup.find(('link', 'a'), {'rel': rel})
  if link and link.get('href'):
    return urllib.parse.urljoin(resp.url, link['href'])


def discover_auth_endpoints(me):
  """Fetches a user's URL and discovers their IndieAuth endpoints.

  Args:
    me (str): URL of the user

  Return:
    (str, str) tuple: authorization endpoint, token endpoint. The token endpoint
    may be None, which means to redeem codes at the authorization endpoint.
  """
  try:
    resp = util.requests_get(me)
  except (ValueError, requests.URLRequired, requests.TooManyRedirects) as e:
    flask_util.error(str(e))

  if not resp.ok:
    logger.warning(f'could not fetch user url {me}, got response {resp.status_code}')
    return INDIELOGIN_URL, INDIELOGIN_TOKEN_URL

  auth_endpoint = discover_endpoint('authorization_endpoint', resp)
  if not auth_endpoint:
    return INDIELOGIN_URL, INDIELOGIN_TOKEN_URL

  return auth_endpoint, discover_endpoint('token_endpoint', resp)


def build_user_json(me):
  """Returns a JSON dict with ``h-card``, ``rel-me`` links, and ``me`` value.

  Args:
    me (str): URL of the user
    resp (requests.Response): response to use

  Return:
    dict: keys include ``me``, the URL for this person; ``h-card``, the
    representative h-card for this page; ``rel-me``, a list of rel-me URLs
    found at this page
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
  in the datastore. Key is the authed ``me`` URL value. See
  :class:`models.BaseAuth` for usage details.
  """
  user_json = ndb.TextProperty(required=True)  # generally this has only 'me'
  access_token_str = ndb.StringProperty()
  refresh_token_str = ndb.StringProperty()

  def site_name(self):
    return 'IndieAuth'

  def user_display_name(self):
    """Returns the user's domain."""
    return self.key_id()

  def image_url(self):
    """Returns the user's profile picture URL, if any."""
    hcard = json_loads(self.user_json).get('h-card', {})
    if photos := hcard.get('properties', {}).get('photo', []):
      return photos[0] if isinstance(photos[0], str) else photos[0].get('value')

  def access_token(self):
    """Return the access token, N/A for IndieAuth"""
    return self.access_token_str


class Start(views.Start):
  """Starts the IndieAuth flow. Requires the ``me`` parameter with the
  user URL that we want to authenticate.

  ``state`` is the :class:`models.PkceCode` datastore key id.
  """
  NAME = 'indieauth'
  LABEL = 'IndieAuth'
  DEFAULT_SCOPE = 'profile'
  SCOPE_SEPARATOR = ' '

  def redirect_url(self, state=None, me=None):
    assert INDIELOGIN_CLIENT_ID, (
      "Please fill in the indielogin_client_id in your app's root directory.")

    # TODO: unify with mastodon?
    if not me:
      me = request.values['me'].strip()
    parsed = urllib.parse.urlparse(me)
    if not parsed.scheme:
      me = 'http://' + me

    auth_endpoint, token_endpoint = discover_auth_endpoints(me)
    redirect_uri = self.to_url()

    # store everything that Callback trusts here, not in the state query param
    code_verifier, code_challenge = pkce.generate_pkce_pair()
    key = models.PkceCode(id=secrets.token_urlsafe(32), verifier=code_verifier,
                          challenge=code_challenge, auth_endpoint=auth_endpoint,
                          token_endpoint=token_endpoint, me=me, state=state).put()

    # construct redirect URL
    return auth_endpoint + '?' + urllib.parse.urlencode({
      'me': me,
      'client_id': INDIELOGIN_CLIENT_ID,
      'redirect_uri': redirect_uri,
      'scope': self.scope,
      'code_challenge': code_challenge,
      'code_challenge_method': 'S256',
      'response_type': 'code',
      'state': key.id(),
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
  Code grant to verify the code.
  """
  def dispatch_request(self):
    code = request.values['code']

    stored = models.PkceCode.get_by_id(request.values['state'])
    if not stored or not stored.me:
      flask_util.error('invalid state parameter')
    stored.key.delete()

    # TODO: fetch server metadata, check that iss matches
    # https://indieauth.spec.indieweb.org/#indieauth-server-metadata
    if (stored.auth_endpoint == INDIELOGIN_URL
        and request.values.get('iss') != INDIELOGIN_ISSUER):
      flask_util.error(f"iss doesn't match {INDIELOGIN_ISSUER}")

    state = stored.state or ''
    data = {
      'grant_type': 'authorization_code',
      'client_id': INDIELOGIN_CLIENT_ID,
      'code': code,
      'redirect_uri': request.base_url,
      'code_verifier': stored.verifier,
    }
    if not stored.token_endpoint:
      # older authorization endpoints may expect these
      data.update({
        'me': stored.me,
        'state': state,
      })

    validate_resp = util.requests_post(stored.token_endpoint or stored.auth_endpoint,
                                       data=data,
                                       headers={'Accept': 'application/json'})

    if (validate_resp.ok
        and (data := util.sniff_json_or_form_encoded(validate_resp.text))):
      if data.get('me'):
        verified = data.get('me')

        # check endpoints, since a site could declare another site's authorization
        # endpoint with its own token endpoint
        if verified != stored.me:
          endpoints = (stored.auth_endpoint, stored.token_endpoint)
          if discover_auth_endpoints(verified) != endpoints:
            flask_util.error(f"{verified} doesn't use the same IndieAuth endpoints as {stored.me}")

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

    flask_util.error(f'IndieAuth verification failed: {validate_resp.status_code} {validate_resp.text}')
