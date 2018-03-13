"""GitHub OAuth drop-in.

API docs:
https://developer.github.com/v4/
https://developer.github.com/apps/building-oauth-apps/authorization-options-for-oauth-apps/#web-application-flow
"""
import json
import logging
import urllib
import urlparse

import appengine_config
import handlers
from models import BaseAuth
from webutil import util

from google.appengine.ext import ndb
from webob import exc

# URL templates. Can't (easily) use urlencode() because I want to keep
# the %(...)s placeholders as is and fill them in later in code.
GET_AUTH_CODE_URL = str('&'.join((
    'https://github.com/login/oauth/authorize?'
    'client_id=%(client_id)s',
    # https://developer.github.com/apps/building-oauth-apps/scopes-for-oauth-apps/
    'scope=%(scope)s',
    # if provided, must be the same in the access token request, or a subpath!
    'redirect_uri=%(redirect_uri)s',
    'state=%(state)s',
    )))

GET_ACCESS_TOKEN_URL = 'https://github.com/login/oauth/access_token'

API_GRAPHQL = 'https://api.github.com/graphql'
# https://developer.github.com/v4/object/user/
GRAPHQL_USER = {
  'query': """
query {
  viewer {
    id
    login
    name
    url
    avatarUrl
    id
    location
    websiteUrl
    bio
  }
}""",
}


class GitHubAuth(BaseAuth):
  """An authenticated GitHub user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the GitHub REST API. Stores OAuth credentials in the datastore.
  See models.BaseAuth for usage details.

  GitHub-specific details: implements get() but not urlopen(), http(), or api().
  The key name is the username.
  """
  access_token_str = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty()

  def site_name(self):
    return 'GitHub'

  def user_display_name(self):
    """Returns the user's full name or username.
    """
    return self.key.string_id()

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def get(self, *args, **kwargs):
    """Wraps requests.get() and adds the Bearer token header.

    TODO: unify with medium.py.
    """
    return self._requests_call(util.requests_get, *args, **kwargs)

  def post(self, *args, **kwargs):
    """Wraps requests.post() and adds the Bearer token header.

    TODO: unify with medium.py.
    """
    return self._requests_call(util.requests_post, *args, **kwargs)

  def _requests_call(self, fn, *args, **kwargs):
    headers = kwargs.setdefault('headers', {})
    headers['Authorization'] = 'Bearer ' + self.access_token_str

    resp = fn(*args, **kwargs)
    assert 'errors' not in resp, resp

    try:
      resp.raise_for_status()
    except BaseException, e:
      util.interpret_http_exception(e)
      raise
    return resp


class StartHandler(handlers.StartHandler):
  """Starts GitHub auth. Requests an auth code and expects a redirect back.
  """
  DEFAULT_SCOPE = ''

  def redirect_url(self, state=None):
    assert (appengine_config.GITHUB_CLIENT_ID and
            appengine_config.GITHUB_CLIENT_SECRET), (
      "Please fill in the github_client_id and "
      "github_client_secret files in your app's root directory.")
    return str(GET_AUTH_CODE_URL % {
      'client_id': appengine_config.GITHUB_CLIENT_ID,
      'redirect_uri': urllib.quote_plus(self.to_url()),
      # TODO: does GitHub require non-empty state?
      'state': urllib.quote_plus(state if state else ''),
      'scope': self.scope,
      })


class CallbackHandler(handlers.CallbackHandler):
  """The OAuth callback. Fetches an access token and stores it.
  """

  def get(self):
    # handle errors
    error = self.request.get('error')
    if error:
      if error == 'access_denied':
        logging.info('User declined')
        self.finish(None, state=self.request.get('state'))
        return
      else:
        msg = 'Error: %s: %s' % (error, self.request.get('error_description'))
        logging.info(msg)
        raise exc.HTTPBadRequest(msg)

    # extract auth code and request access token
    auth_code = util.get_required_param(self, 'code')
    data = {
      'code': auth_code,
      'client_id': appengine_config.GITHUB_CLIENT_ID,
      'client_secret': appengine_config.GITHUB_CLIENT_SECRET,
      # redirect_uri here must be the same in the oauth code request!
      # (the value here doesn't actually matter since it's requested server side.)
      'redirect_uri': self.request.path_url,
      }
    resp = util.requests_post(GET_ACCESS_TOKEN_URL,
                              data=urllib.urlencode(data)).text
    logging.debug('Access token response: %s', resp)

    resp = urlparse.parse_qs(resp)

    error = resp.get('error')
    if error:
      msg = 'Error: %s: %s' % (error[0], resp.get('error_description'))
      logging.info(msg)
      raise exc.HTTPBadRequest(msg)

    access_token = resp['access_token'][0]
    resp = GitHubAuth(access_token_str=access_token).post(
        API_GRAPHQL, json=GRAPHQL_USER).json()
    logging.debug('GraphQL data.viewer response: %s', resp)
    user_json = resp['data']['viewer']
    auth = GitHubAuth(id=user_json['login'], access_token_str=access_token,
                      user_json=json.dumps(user_json))
    auth.put()

    self.finish(auth, state=self.request.get('state'))
