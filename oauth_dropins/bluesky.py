from atproto.exceptions import UnauthorizedError
from . import views, models
from flask import request
from google.cloud import ndb
from .webutil.util import json_dumps
import atproto

class Start(views.Start):
  """
  Starts Bluesky auth - used just to provide the button.
  """
  NAME = 'bluesky'
  LABEL = 'Bluesky'

class BlueskyAuth(models.BaseAuth):
  """
  An authenticated Bluesky user.
  """

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
    Returns an atproto.Client.
    """
    (client, _) = BlueskyAuth._api_from_password(self.did, self.password)
    return client

  @staticmethod
  def _api_from_password(handle, password):
    client = atproto.Client()
    profile = client.login(handle, password)
    return (client, profile)


class Callback(views.Callback):
  """
  OAuth callback stub.
  """
  def dispatch_request(self):
    username = request.values['username']
    password = request.values['password']

    # get the did (portable user ID)
    try:
      # TODO migrate this to lexrpc
      (_, profile) = BlueskyAuth._api_from_password(username, password)
    except UnauthorizedError:
      return self.finish(None)
    user_json = json_dumps({
      '$type': profile._type,
      'did': profile.did,
      'handle': profile.handle,
      'avatar': profile.avatar,
      'banner': profile.banner,
      'displayName': profile.displayName,
      'description': profile.description,
    })
    auth = BlueskyAuth(
      id=profile.did,
      did=profile.did,
      password=password,
      user_json=user_json,
    )
    auth.put()
    return self.finish(auth)
