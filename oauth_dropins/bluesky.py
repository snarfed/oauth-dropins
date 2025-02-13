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
from requests_oauth2client import (
  AuthorizationRequestSerializer,
  OAuth2Client,
  OAuth2Error,
  OAuth2AccessTokenAuth,
)

from . import views, models
from .webutil import flask_util, util
from .webutil.models import JsonProperty

logger = logging.getLogger(__name__)

os.environ.setdefault('PLC_HOST', 'plc.directory')

# https://docs.bsky.app/docs/advanced-guides/oauth-client#client-and-server-metadata
PROTECTED_RESOURCE_PATH = '/.well-known/oauth-protected-resource'
RESOURCE_METADATA_PATH = '/.well-known/oauth-authorization-server'
CLIENT_METADATA_TEMPLATE = {
  # Clients must fill these in
  'client_id': None,      # eg 'https://app.example.com/oauth/client-metadata.json'
  'client_name': None,    # eg 'My Example App'
  'client_uri': None,     # eg 'https://app.example.com'
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


class BlueskyLogin(ndb.Model):
  """An in-progress Bluesky OAuth login. Ephemeral.

  Stores a serialized :class:`requests_oauth2client.AuthorizationRequest` across
  HTTP requests.
  """  state = ndb.TextProperty()
  authz_request = ndb.TextProperty(required=True)
  """Serialized :class:`requests_oauth2client.AuthorizationRequest`.

  Uses :meth:`requests_oauth2client.AuthorizationRequestSerializer.default_dumper` /
  :meth:`requests_oauth2client.AuthorizationRequestSerializer.default_loader`.
  """

  @classmethod
  def load(cls, id):
    if not util.is_int(id):
      flask_util.error(f'State {id} not found')

    login = cls.get_by_id(int(id))
    if not login:
      flask_util.error(f'State {id} not found')

    return login


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
    * :attr:`CLIENT_METADATA` (dict): client info metadata,
      https://docs.bsky.app/docs/advanced-guides/oauth-client#client-and-server-metadata
  """
  CLIENT_METADATA = None
  SCOPE = CLIENT_METADATA_TEMPLATE['scope']

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

    assert self.CLIENT_METADATA
    client_id = self.CLIENT_METADATA['client_id']

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

    # generate authz URL, store session, redirect
    client = OAuth2Client.from_discovery_endpoint(
      urljoin(auth_server, RESOURCE_METADATA_PATH),
      client_id=self.CLIENT_METADATA['client_id'],
      redirect_uri='https://oauth-dropins.appspot.com/bluesky/oauth_callback',#self.to_url()
      dpop_bound_access_tokens=True,
    )

    login_key = BlueskyLogin.allocate_ids(1)[0]
    try:
      authz_request = client.authorization_request(scope=self.SCOPE,
                                                   state=login_key.id())
      logger.warning(authz_request.state)
      par_request = client.pushed_authorization_request(authz_request)
    except OAuth2Error as e:
      err(e)

    serialized = AuthorizationRequestSerializer.default_dumper(authz_request)
    BlueskyLogin(key=login_key, state=state, authz_request=serialized).put()

    return par_request.uri


class OAuthCallback(views.Callback):
  """Finishes the OAuth flow.

  Subclasses must populate:
    * :attr:`CLIENT_METADATA` (dict): client info metadata,
      https://docs.bsky.app/docs/advanced-guides/oauth-client#client-and-server-metadata
  """
  CLIENT_METADATA = None

  def dispatch_request(self):
    # handle errors
    error = request.values.get('error')
    desc = request.values.get('error_description')
    if error:
      msg = f'Error: {error}: {desc}'
      logger.info(msg)
      if error == 'access_denied':
        return self.finish(None, state=request.values.get('state'))
      else:
        flask_util.error(msg)

    login = BlueskyLogin.load(request.values['state'])
    try:
      # validate authz response
      authz_request = AuthorizationRequestSerializer.default_loader(
        login.authz_request)
      authz_resp = authz_request.validate_callback(
        # XXX TODO
        request.url.replace('http://localhost:8080/', 'https://oauth-dropins.appspot.com/'))

      # get access token
      client = OAuth2Client.from_discovery_endpoint(
        # XXX TODO
        urljoin('https://bsky.social', RESOURCE_METADATA_PATH),
        client_id=self.CLIENT_METADATA['client_id'],
        redirect_uri='https://oauth-dropins.appspot.com/bluesky/oauth_callback',#request.base_url,
        dpop_bound_access_tokens=True,
      )
      token = client.authorization_code(authz_resp)
    except OAuth2Error as e:
      flask_util.error(e)

    session = requests.Session()
    session.auth = OAuth2AccessTokenAuth(client=client, token=token)

    did = 'did:plc:fdme4gb7mu7zrie7peay7tst'
    try:
      resp = session.get(f'https://enoki.us-east.host.bsky.network/xrpc/app.bsky.actor.getProfile?actor={did}')
      resp.raise_for_status()
    except BaseException as e:
      code, body = util.interpret_http_exception(e)
      if code:
        flask_util.error(f'{e.status_code}')
      raise

    auth = BlueskyAuth(id=did, session=session, user_json=util.json_dumps({
      '$type': 'app.bsky.actor.defs#profileViewDetailed',
      **resp.json(),
    }))
    auth.put()
    return self.finish(auth, state=login.state)
