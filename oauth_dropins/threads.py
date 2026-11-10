"""Threads OAuth 2 drop-in.

https://developers.facebook.com/docs/threads/
"""
import logging

from flask import request
from google.cloud import ndb
import requests
from requests_oauth2client import BearerToken, OAuth2Client
from webutil import flask_util, util
from webutil.util import json_dumps, json_loads

from . import models, views

logger = logging.getLogger(__name__)

APP_ID = util.read('threads_app_id')
APP_SECRET = util.read('threads_app_secret')

AUTH_CODE_URL = 'https://threads.net/oauth/authorize'
ACCESS_TOKEN_URL = 'https://graph.threads.net/oauth/access_token'
API_ACCOUNT_URL = 'https://graph.threads.net/v1.0/me?fields=id,username,name,threads_profile_picture_url,threads_biography'

# https://developers.facebook.com/docs/threads/get-started/get-access-tokens-and-permissions
ALL_SCOPES = (
  'threads_basic',
  'threads_content_publish',
  'threads_read_replies',
  'threads_manage_replies',
  'threads_manage_insights',
)


def https_if_localhost(url):
  return (url.replace('http://', 'https://', 1)
          if url.startswith('http://localhost:8080/')
          else url)


class ThreadsAuth(models.BaseAuth):
  """An OAuth-authenticated Threads user.

  Provides methods that return information about this user and store OAuth 2 tokens
  in the datastore. See models.BaseAuth for usage details.

  The datastore entity key name is the integer user id.
  """
  # Fields: access_token, token_type, user_id
  token_json = ndb.TextProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Threads'

  def user_display_name(self):
    """Returns the username."""
    return json_loads(self.user_json).get('username')

  def image_url(self):
    """Returns the user's profile picture URL, if any."""
    return json_loads(self.user_json).get('threads_profile_picture_url')

  def access_token(self):
    """Returns the OAuth access token JSON."""
    return json_loads(self.token_json)['access_token']

  def session(self):
    """Returns a :class:`requests.Session` that uses this user's access token."""
    session = requests.Session()
    session.auth = BearerToken(self.access_token())
    return session


class Start(views.Start):
  """Starts three-legged OAuth with Threads.

  Redirects to Threads's auth prompt for user approval.
  """
  NAME = 'threads'
  LABEL = 'Threads'
  DEFAULT_SCOPE = 'threads_basic'

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args,
      input_style='background-color: #EEEEEE',
      **kwargs)

  def to_url(self, state=None):
    return https_if_localhost(super().to_url(state=state))

  def redirect_url(self, state=None):
    assert APP_ID and APP_SECRET, \
      "Please fill in the threads_app_key and threads_app_secret files in your app's root directory."

    # redirect to Threads auth URL
    client = OAuth2Client(token_endpoint=ACCESS_TOKEN_URL,
                          authorization_endpoint=AUTH_CODE_URL,
                          client_id=APP_ID,
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

    client = OAuth2Client(token_endpoint=ACCESS_TOKEN_URL, client_id=APP_ID,
                          client_secret=APP_SECRET, session=util.session)
    token = client.authorization_code(
      request.values['code'], redirect_uri=https_if_localhost(request.base_url))
    logger.info(f'Got access token for user {token.user_id}')

    # Fetch user info
    resp = util.requests_get(API_ACCOUNT_URL, auth=token)
    resp.raise_for_status()
    user_json = resp.json()
    logging.info(user_json)

    auth = ThreadsAuth(id=str(token.user_id),
                       token_json=json_dumps(token.as_dict()),
                       user_json=json_dumps(user_json))
    auth.put()

    return self.finish(auth, state=request.values.get('state'))
