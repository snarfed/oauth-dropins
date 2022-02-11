"""Disqus OAuth drop-in.

Disqus API docs: https://disqus.com/api/docs/

This drop-in is even more similar to Instagram than Instagram is to
Facebook. Differences:

- urlopen must pass the api_key with each request (in addition to the
  access_token)
- Response to access_token does not give much information about the user,
  so we additionally fetch /user/details before saving
- Deny appears to be broken on Disqus's side (clicking "No Thanks" has
  no effect), so we ignore that possibility for now.

TODO unify Disqus, Facebook, and Instagram
"""
import logging
import urllib.parse

from flask import request
from google.cloud import ndb

from . import models, views
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

DISQUS_CLIENT_ID = util.read('disqus_client_id')
DISQUS_CLIENT_SECRET = util.read('disqus_client_secret')
GET_AUTH_CODE_URL = (
    'https://disqus.com/api/oauth/2.0/authorize/?' +
    '&'.join((
        'client_id=%(client_id)s',
        'scope=%(scope)s',
        'response_type=code',
        'redirect_uri=%(redirect_uri)s',
    )))
GET_ACCESS_TOKEN_URL = 'https://disqus.com/api/oauth/2.0/access_token/'
USER_DETAILS_URL = 'https://disqus.com/api/3.0/users/details.json?user=%d'


class DisqusAuth(models.BaseAuth):
  """An authenticated Disqus user.

  Provides methods that return information about this user (or page)
  and make OAuth-signed requests to Instagram's HTTP-based
  APIs. Stores OAuth credentials in the datastore. See models.BaseAuth
  for usage details.

  Disqus-specific details: implements urlopen() but not api().
  The key name is the Disqus user id.
  """
  auth_code = ndb.StringProperty(required=True)
  access_token_str = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Disqus'

  def user_display_name(self):
    """Returns the user's name.
    """
    return json_loads(self.user_json)['name']

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def urlopen(self, url, **kwargs):
    """Wraps urlopen() and adds OAuth credentials to the request.
    """
    # TODO does work for POST requests? key is always passed as a
    # query param, regardless of method.
    return models.BaseAuth.urlopen_access_token(url, self.access_token_str,
                                                DISQUS_CLIENT_ID, **kwargs)


class Start(views.Start):
  """Starts Disqus auth. Requests an auth code and expects a redirect back.
  """
  NAME = 'disqus'
  LABEL = 'Disqus'

  # Disqus scopes are comma separated: read, write, admin, email
  # https://disqus.com/api/docs/requests/#data-availability
  DEFAULT_SCOPE = 'read'

  def redirect_url(self, state=None):
      assert DISQUS_CLIENT_ID and DISQUS_CLIENT_SECRET, \
          "Please fill in the disqus_client_id and disqus_client_secret files in your app's root directory."
      return GET_AUTH_CODE_URL % {
        'client_id': DISQUS_CLIENT_ID,
        'scope': self.scope,
        'redirect_uri': urllib.parse.quote_plus(self.to_url(state=state)),
      }


class Callback(views.Callback):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """
  def dispatch_request(self):
    if self.handle_error():
      return

    # https://disqus.com/api/docs/auth/
    auth_code = request.values['code']
    data = {
        'grant_type': 'authorization_code',
        'client_id': DISQUS_CLIENT_ID,
        'client_secret': DISQUS_CLIENT_SECRET,
        'redirect_uri': self.request_url_with_state(),
        'code': auth_code,
    }

    resp = util.requests_post(GET_ACCESS_TOKEN_URL, data=data)
    resp.raise_for_status()
    try:
      data = json_loads(resp.text)
    except (ValueError, TypeError):
      logger.error(f'Bad response:\n{resp}', exc_info=True)
      flask_util.error('Bad Disqus response to access token request')

    access_token = data['access_token']
    user_id = data['user_id']
    # TODO is a username key preferred?
    # username = data['username']

    auth = DisqusAuth(id=str(user_id),
                      auth_code=auth_code,
                      access_token_str=access_token)

    resp = auth.urlopen(USER_DETAILS_URL % user_id).read()
    try:
      user_data = json_loads(resp)['response']
    except (ValueError, TypeError):
      logger.error(f'Bad response:\n{resp}', exc_info=True)
      flask_util.error('Bad Disqus response to user details request')

    auth.user_json = json_dumps(user_data)
    logger.info(f'created disqus auth {auth}')
    auth.put()
    return self.finish(auth, state=request.values.get('state'))

  def handle_error(handler):
    """Handles any error reported in the callback query parameters.

    Args:
      handler: Callback

    Returns:
      True if there was an error, False otherwise.
    """
    error = request.values.get('error')
    if error:
      if error == 'access_denied':
        logger.info('User declined')
        handler.finish(None, state=request.values.get('state'))
        return True
      else:
        flask_util.error(error)

    return False
