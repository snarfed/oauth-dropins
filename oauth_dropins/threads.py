"""Threads OAuth 2 drop-in.

https://developers.facebook.com/docs/threads/
"""
import logging

from flask import request
from google.cloud import ndb
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session

from . import models, views
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

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
  # Fields: token_type, access_token, scope, expires_at, expires_in
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
    """Returns a :class:`requests_oauthlib.OAuth2Session`."""
    token = json_loads(self.token_json)

    if token.get('refresh_token') and token.get('expires_at'):
      def update_token(token):
        logging.info(f'Storing new access token {token}')
        self.token = token
        self.put()

      kwargs = {
        'auto_refresh_url': ACCESS_TOKEN_URL,
        'auto_refresh_kwargs': {'client_id': APP_ID},
        'token_updater': update_token,
      }

    session = OAuth2Session(APP_ID, token=token, **kwargs)
    session.auth = HTTPBasicAuth(APP_ID, APP_SECRET)
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
    session = OAuth2Session(APP_ID, scope=self.scope, redirect_uri=self.to_url())
    auth_url, state = session.authorization_url(AUTH_CODE_URL, state=state)
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

    session = OAuth2Session(APP_ID, redirect_uri=https_if_localhost(request.base_url))
    session.fetch_token(ACCESS_TOKEN_URL, include_client_id=True,
                        client_secret=APP_SECRET, authorization_response=request.url)
    logging.info(f'Got access token {session.token}')

    # Fetch user info
    resp = util.requests_get(API_ACCOUNT_URL, session=session)
    resp.raise_for_status()
    user_json = resp.json()
    logging.info(user_json)

    auth = ThreadsAuth(id=str(session.token['user_id']),
                       token_json=json_dumps(session.token),
                       user_json=json_dumps(user_json))
    auth.put()

    return self.finish(auth, state=request.values.get('state'))
