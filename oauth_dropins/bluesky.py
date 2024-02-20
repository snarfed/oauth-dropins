"""Bluesky auth drop-in.

Not actually OAuth yet, they currently use app passwords.
https://atproto.com/specs/xrpc#app-passwords
"""
import logging

from flask import request
from google.cloud import ndb
from lexrpc import Client

from . import views, models
from .webutil import util
from .webutil.models import JsonProperty

logger = logging.getLogger(__name__)


class Start(views.Start):
  """
  Starts Bluesky auth - used just to provide the button.
  """
  NAME = 'bluesky'
  LABEL = 'Bluesky'

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args,
      image_file='bluesky_logotype.png',
      input_style='background-color: #EEEEEE',
      **kwargs)


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


class Callback(views.Callback):
  """
  OAuth callback stub.
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
