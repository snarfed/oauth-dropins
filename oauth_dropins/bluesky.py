"""Bluesky/AT Protocol OAuth drop-in.

https://atproto.com/docs

Requires app passwords: https://atproto.com/specs/atp#app-passwords
"""
import logging
from urllib.parse import quote_plus, unquote, urlencode, urljoin, urlparse, urlunparse

from flask import request
from google.cloud import ndb
import requests

from . import views
from .models import BaseAuth
from .webutil import appengine_info, flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

DOMAINS = (
  'bsky.app',
  'staging.bsky.app',
)


class BlueskyAuth(BaseAuth):
  """An authenticated Bluesky user.

  Provides methods that return information about this user and make authenticated
  requests to the Bluesky REST API. Stores app password in the datastore.
  See models.BaseAuth for usage details.

  Key name is the user's handle, eg alice.bsky.social.

  Implements get() and post() but not urlopen() or api().
  """
  app = ndb.KeyProperty()
  app_password = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty()

  def site_name(self):
    return 'Bluesky'

  def user_display_name(self):
    """Returns the user's display name, eg 'Alice'."""
    return self.key.id()

  def instance(self):
    """Returns the instance base URL, eg 'https://bsky.app/'."""
    return self.app.get().instance

  def username(self):
    """Returns the user's domain handle, eg alice.bsky.social."""
    return json_loads(self.user_json).get(...)

  def did(self):
    """Returns the user's id, eg 'did:plc:abc123'."""
    return ...

  def get(self, *args, **kwargs):
    """Wraps requests.get() and adds instance base URL and Bearer token header."""
    url = urljoin(self.instance(), args[0])
    return self._requests_call(util.requests_get, url, *args[1:], **kwargs)

  def post(self, *args, **kwargs):
    """Wraps requests.post() and adds the Bearer token header."""
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


def start():
  """Flask handler. Authenticates and fetches the user's profile.

  Attributes:
    ...
  """
  NAME = 'bluesky'
  LABEL = 'Bluesky'

  TODO
  ...

  # normalize instance to URL
  if not instance:
    instance = request.values['instance']
  instance = instance.strip().split('@')[-1]  # handle addresses, eg user@host.com
  parsed = urlparse(instance)
  if not parsed.scheme:
    instance = 'https://' + instance

  app_data = json_loads(app.data)
  return urljoin(instance, AUTH_CODE_API % {
    'client_id': app_data['client_id'],
    'client_secret': app_data['client_secret'],
    'redirect_uri': quote_plus(self.to_url()),
    'state': _store_state(app, state),
    'scope': self.scope,
  })

  @classmethod
  def button_html(cls, *args, **kwargs):
    kwargs['form_extra'] = kwargs.get('form_extra', '') + f"""
<input type="url" name="instance" class="form-control" placeholder="{cls.LABEL} instance" scheme="https" required style="width: 135px; height: 50px; display:inline;" />"""
    return super(Start, cls).button_html(
      *args, input_style='background-color: #EBEBEB; padding: 5px', **kwargs)
