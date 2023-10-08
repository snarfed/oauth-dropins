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

logger = logging.getLogger(__name__)


class Start(views.Start):
  """
  Starts Bluesky auth - used just to provide the button.
  """
  NAME = 'bluesky'
  LABEL = 'Bluesky'


class BlueskyAuth(models.BaseAuth):
  """An authenticated Bluesky user."""
  did = ndb.StringProperty(required=True)
  password = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Bluesky'

  def access_token(self):
    """
    Returns did and password as a tuple in place of an OAuth key id/secret pair.
    """
    return (self.did, self.password)

  def _api(self):
    """
    Returns:
      lexrpc.Client:
    """
    return self._api_from_password(self.did, self.password)

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
    client = Client('https://bsky.social', headers={'User-Agent': util.user_agent})
    resp = client.com.atproto.server.createSession({
        'identifier': handle,
        'password': password,
      })
    logger.info(f'Got DID {resp["did"]}')

    client.access_token = resp['accessJwt']
    return client


class Callback(views.Callback):
  """
  OAuth callback stub.
  """
  def dispatch_request(self):
    handle = request.values['username']
    password = request.values['password']

    # get the did (portable user ID)
    try:
      client = BlueskyAuth._api_from_password(handle, password)
    except ValueError as e:
      logger.warning(f'Login failed: {e}')
      return self.finish(None)

    profile = {
      '$type': 'app.bsky.actor.defs#profileViewDetailed',
      **client.app.bsky.actor.getProfile(actor=handle)
    }
    auth = BlueskyAuth(
      id=profile['did'],
      did=profile['did'],
      password=password,
      user_json=util.json_dumps(profile),
    )
    auth.put()
    return self.finish(auth)
