"""Twitter OAuth 2 drop-in.

https://developer.twitter.com/en/docs/authentication/oauth-2-0/user-access-token
https://developer.twitter.com/en/docs/authentication/oauth-2-0/authorization-code
https://developer.twitter.com/en/docs/authentication/api-reference/token
"""
import logging
import secrets
import time

from flask import request
from google.cloud import ndb
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session
from urllib.parse import quote_plus, unquote, urlencode, urljoin, urlparse, urlunparse

from . import models, views
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

TWITTER_CLIENT_ID = util.read('twitter_app_key')
TWITTER_CLIENT_SECRET = util.read('twitter_app_secret')

AUTH_CODE_URL = 'https://twitter.com/i/oauth2/authorize'
ACCESS_TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'
API_ACCOUNT_URL = 'https://api.twitter.com/2/users/me'

# https://developer.twitter.com/en/docs/authentication/oauth-2-0/authorization-code
ALL_SCOPES = (
  'block.read',
  'block.write',
  'bookmark.read',
  'bookmark.write',
  'follows.read',
  'follows.write',
  'like.read',
  'like.write',
  'list.read',
  'list.write',
  'mute.read',
  'mute.write',
  'offline.access',
  'space.read',
  'tweet.read',
  'tweet.write',
  'users.read',
)


class TwitterOAuth2(models.BaseAuth):
  """An OAuth2-authenticated Twitter user.

  Provides methods that return information about this user and store OAuth 2 tokens
  in the datastore. See models.BaseAuth for usage details.

  The datastore entity key name is the Twitter username.
  """
  # Fields: token_type, access_token, scope, expires_at, expires_in
  token_json = ndb.TextProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Twitter'

  def user_display_name(self):
    """Returns the username."""
    return self.key_id()

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
        'auto_refresh_kwargs': {'client_id': TWITTER_CLIENT_ID},
        'token_updater': update_token,
      }

    session = OAuth2Session(TWITTER_CLIENT_ID, token=token, **kwargs)
    session.auth = HTTPBasicAuth(TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET)
    return session


class Start(views.Start):
  """Starts three-legged OAuth with Twitter.

  Redirects to Twitter's auth prompt for user approval.
  """
  NAME = 'twitter'
  LABEL = 'Twitter'
  SCOPE_SEPARATOR = ' '
  DEFAULT_SCOPE = 'tweet.read users.read'

  def redirect_url(self, state=None):
    assert TWITTER_CLIENT_ID and TWITTER_CLIENT_SECRET, \
      "Please fill in the twitter_app_key and twitter_app_secret files in your app's root directory."

    if not state:
      state = secrets.token_urlsafe(32)
      logging.debug(f'No state provided; generated default random state {state}')

    # generate and store PKCE code
    verifier = secrets.token_urlsafe(64)
    key = models.PkceCode(id=state, challenge=verifier, verifier=verifier).put()
    logging.info(f'Storing PKCE code verifier {verifier}: {key}')

    # redirect to Twitter auth URL
    session = OAuth2Session(TWITTER_CLIENT_ID, scope=self.scope,
                            redirect_uri=self.to_url())
    auth_url, state = session.authorization_url(
      AUTH_CODE_URL, state=state,
      code_challenge=verifier,
      code_challenge_method='plain')
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

    # look up PKCE code verifier
    code = models.PkceCode.get_by_id(state)
    if not code:
      flask_util.error(f'state not found: {state}')
    logging.info(f'Loaded PKCE code {code}')

    session = OAuth2Session(TWITTER_CLIENT_ID, redirect_uri=request.base_url)
    session.fetch_token(ACCESS_TOKEN_URL, code=request.values['code'],
                        client_secret=TWITTER_CLIENT_SECRET,
                        authorization_response=request.url,
                        code_verifier=code.verifier)
    logging.info(f'Got access token {session.token}')

    # Fetch user info
    resp = util.requests_get(API_ACCOUNT_URL, session=session)
    resp.raise_for_status()
    user_json = resp.json()
    logging.info(f'{user_json}')
    username = user_json['data']['username']

    auth = TwitterOAuth2(id=username, token_json=json_dumps(session.token),
                         user_json=json_dumps(user_json))
    auth.put()

    return self.finish(auth, state=request.values.get('state'))
