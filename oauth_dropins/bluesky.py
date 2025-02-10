"""Bluesky auth drop-in. Supports both app password login and OAuth.

Use :class:`PasswordStart` and :class:`PasswordCallback` for app password,
class:`OAuthStart` and :class:`OAuthCallback` for OAuth.

https://atproto.com/specs/xrpc#:~:text=App,passwords
https://docs.bsky.app/docs/advanced-guides/oauth-client
https://atproto.com/specs/oauth

OAuth 2 here is implemented from scratch :( since I couldn't find a Python
library that implemented PAR (pushed authorization request).
"""
import logging
import os
import re
from urllib.parse import urljoin

import arroba.did
from flask import request
from google.cloud import ndb
from lexrpc import Client
import requests

from . import views, models
from .webutil import util
from .webutil.models import JsonProperty

logger = logging.getLogger(__name__)

os.environ.setdefault('PLC_HOST', 'plc.directory')

# https://docs.bsky.app/docs/advanced-guides/oauth-client#client-and-server-metadata
PROTECTED_RESOURCE_PATH = '/.well-known/oauth-protected-resource'
RESOURCE_METADATA_PATH = '/.well-known/oauth-authorization-server'
CLIENT_METADATA_TEMPLATE = {
  # Clients must fill these in
  'client_id': None,     # eg 'https://app.example.com/oauth/client-metadata.json'
  'client_name': None,   # eg 'My Example App'
  'client_uri': None,    # eg 'https://app.example.com'
  'redirect_uris': None,  # eg ['https://app.example.com/oauth/callback'],

  # standard
  'application_type': 'web',
  'dpop_bound_access_tokens': True,
  'grant_types': [
    'authorization_code',
    'refresh_token',
  ],
  'response_types': ['code'],
  'scope': 'atproto transition:generic',
  'token_endpoint_auth_method': 'none',
}

_APP_CLIENT_METADATA = {
  **CLIENT_METADATA_TEMPLATE,
  'client_id': 'https://oauth-dropins.appspot.com/bluesky/client-metadata.json',
  'client_name': 'oauth-dropins demo',
  'client_uri': 'https://oauth-dropins.appspot.com/',
  'redirect_uris': ['https://oauth-dropins.appspot.com/bluesky/oauth_callback'],
}


class BlueskyAuth(models.BaseAuth):
  """An authenticated Bluesky user.

  Key id is DID.
  """
  password = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)
  session = JsonProperty()

  def site_name(self):
    return 'Bluesky'

  def access_token(self):
    """
    Returns:
      str:
    """
    if self.session:
      return self.session.get('accessJwt')

  def _api(self):
    """
    Returns:
      lexrpc.Client:
    """
    client = Client(headers={'User-Agent': util.user_agent})
    client.session = self.session
    return client

  @staticmethod
  def _api_from_password(handle, password):
    """
    Args:
      handle (str)
      password (str)

    Returns:
      lexrpc.Client:
    """
    logger.info(f'Logging in with handle {handle}...')
    client = Client(headers={'User-Agent': util.user_agent})
    resp = client.com.atproto.server.createSession({
        'identifier': handle,
        'password': password,
      })
    logger.info(f'Got DID {resp["did"]}')
    return client


class StartBase(views.Start):
  """Base class for starting Bluesky auth; only used to provide the button.
  """
  NAME = 'bluesky'
  LABEL = 'Bluesky'

  @classmethod
  def button_html(cls, *args, **kwargs):
    kwargs['form_extra'] = kwargs.get('form_extra', '') + f"""
<input name="handle" class="form-control" placeholder="{cls.LABEL} handle" required style="width: 135px; height: 50px; display:inline;" />"""
    return super(cls, cls).button_html(
      *args,
      image_file='bluesky_logo.png',
      input_style='background-color: #EEEEEE',
      **kwargs)

Start = StartBase


class PasswordCallback(views.Callback):
  """
  App password login callback stub.
  """
  def dispatch_request(self):
    handle = request.values['username'].strip().lower().removeprefix('@')
    password = request.values['password'].strip()
    state = request.values.get('state')

    # get the DID (portable user ID)
    try:
      client = BlueskyAuth._api_from_password(handle, password)
    except ValueError as e:
      logger.warning(f'Login failed: {e}')
      return self.finish(None, state=state)

    profile = {
      '$type': 'app.bsky.actor.defs#profileViewDetailed',
      **client.app.bsky.actor.getProfile(actor=handle)
    }
    auth = BlueskyAuth(
      id=profile['did'],
      password=password,
      user_json=util.json_dumps(profile),
      session=client.session,
    )
    auth.put()
    return self.finish(auth, state=state)

Callback = PasswordCallback


class OAuthStart(StartBase):
  """Starts the OAuth flow.

  Subclasses must populate:
    * :attr:`CLIENT_ID`
    * :attr:`CLIENT_METADATA` (dict): client info metadata,
      https://docs.bsky.app/docs/advanced-guides/oauth-client#client-and-server-metadata
  """
  CLIENT_ID = None
  CLIENT_METADATA = None

  # available scopes as of Feb 2025:
  # atproto, transition:generic, transition:chat.bsky
  # https://bsky.social/.well-known/oauth-authorization-server
  DEFAULT_SCOPE = 'atproto transition:generic'
  SCOPE_SEPARATOR = ' '

  def redirect_url(self, state=None, handle=None):
    """Returns the URL for Bluesky to redirect back to after the OAuth prompt.

    Args:
      state (str): user-provided value to be returned as a query parameter in
        the return redirect
      handle (str): Bluesky domain handle. If ````None``, uses the ``handle``
        parameter in POST form data.

    Raises:
      ValueError, RequestException: if handle isn't a valid domain
    """
    def err(msg):
      logger.warning(msg)
      raise ValueError(msg)

    assert self.CLIENT_ID

    if not handle:
      handle = request.form['handle']

    if not re.fullmatch(util.DOMAIN_RE, handle):
      err(f"{handle} doesn't look like a domain")

    # resolve handle to DID doc and PDS base URL
    # https://atproto.com/specs/handle#handle-resolution
    did = arroba.did.resolve_handle(handle)
    if not did:
      err(f"Couldn't resolve {handle} as a Bluesky handle")
    logger.info(f'resolved {handle} to {did}')

    did_doc = arroba.did.resolve(did)
    if not did_doc:
      err(f"Couldn't resolve DID {did}")

    # based on bridgy_fed.atproto.ATProto.pds_for
    for service in did_doc.get('service', []):
      if service.get('id') in ('#atproto_pds', f'{did}#atproto_pds'):
        pds_url = service.get('serviceEndpoint')
        break
    else:
      err(f"{id}'s DID doc has no ATProto PDS")
    logger.info(f'{did} has PDS URL {pds_url}')

    resp = util.requests_get(urljoin(pds_url, PROTECTED_RESOURCE_PATH))
    resp.raise_for_status()
    auth_server = resp.json()['authorization_servers'][0]
    logger.info(f'PDS {pds_url} has auth server {auth_server}')

    resp = util.requests_get(urljoin(auth_server, RESOURCE_METADATA_PATH))
    resp.raise_for_status()
    par_endpoint = resp.json()['pushed_authorization_request_endpoint']
    logger.info(f'pushed_authorization_request_endpoint is {par_endpoint}')

    resp = util.requests_post(par_endpoint, data={
      'client_id': self.CLIENT_ID,
      'scopes': self.scope,
      'redirect_uri': self.to_url(),
      'state': state,
      'login_hint': handle,
    })

    session = OAuth2Session(self.CLIENT_ID, scope=self.scope,
                            redirect_uri=self.to_url())
    auth_url, state = session.authorization_url(
      par_endpoint, state=state, include_granted_scopes='true',
      # ask for a refresh token so we can get an access token offline
      access_type='offline', prompt='consent')

    return auth_url


class OAuthCallback(views.Callback):
  """Finishes the OAuth flow."""

  def dispatch_request(self):
    # handle errors
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

    # extract auth code and request access token
    session = OAuth2Session(google_signin.GOOGLE_CLIENT_ID, scope=self.scope,
                            redirect_uri=request.base_url)
    session.fetch_token(ACCESS_TOKEN_URL,
                        client_secret=google_signin.GOOGLE_CLIENT_SECRET,
                        authorization_response=request.url)

    client = BloggerV2Auth(creds_json=json_dumps(session.token)).api()
    # ...
    auth = BloggerV2Auth(id=id,
                         name=author.name.text,
                         picture_url=picture_url,
                         creds_json=json_dumps(session.token),
                         user_atom=str(author),
                         blogs_atom=str(blogs),
                         blog_ids=blog_ids,
                         blog_titles=blog_titles,
                         blog_hostnames=blog_hostnames)
    auth.put()
    return self.finish(auth, state=state)
