"""Medium OAuth drop-in.

API docs:
https://github.com/Medium/medium-api-docs#contents
https://medium.com/developers/welcome-to-the-medium-api-3418f956552

Medium doesn't let you use a localhost redirect URL. :/ A common workaround is
to map an arbitrary host to localhost in your /etc/hosts, e.g.:

127.0.0.1 my.dev.com

You can then test on your local machine by running dev_appserver and opening
http://my.dev.com:8080/ instead of http://localhost:8080/ .
"""

import json
import logging
import urllib

import appengine_config
import handlers
from models import BaseAuth
from webutil import util

from google.appengine.ext import ndb
from webob import exc

# medium is behind cloudflare, which often blocks requests's user agent, so set
# our own.
USER_AGENT = 'oauth-dropins (https://oauth-dropins.appspot.com/)'

# URL templates. Can't (easily) use urllib.urlencode() because I want to keep
# the %(...)s placeholders as is and fill them in later in code.
GET_AUTH_CODE_URL = str('&'.join((
    'https://medium.com/m/oauth/authorize?'
    'client_id=%(client_id)s',
    # https://github.com/Medium/medium-api-docs#user-content-21-browser-based-authentication
    # basicProfile, listPublications, publishPost, uploadImage
    'scope=%(scope)s',
    # redirect_uri here must be the same in the access token request!
    'redirect_uri=%(redirect_uri)s',
    'state=%(state)s',
    'response_type=code',
    )))

API_BASE = 'https://api.medium.com/v1/'
GET_ACCESS_TOKEN_URL = API_BASE + 'tokens'
API_USER_URL = API_BASE + 'me'


class MediumAuth(BaseAuth):
  """An authenticated Medium user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the Medium REST API. Stores OAuth credentials in the datastore.
  See models.BaseAuth for usage details.

  Medium-specific details: implements get() but not urlopen(), http(), or api().
  The key name is the user id (*not* username).
  """
  access_token_str = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty()
  # used by bridgy in
  # https://github.com/snarfed/bridgy/commit/58cce60790e746d300e7e5dac331543c56bd9108
  # background: https://github.com/snarfed/bridgy/issues/506
  publications_json = ndb.TextProperty()

  def site_name(self):
    return 'Medium'

  def user_display_name(self):
    """Returns the user's full name or username.
    """
    if self.user_json:
      data = json.loads(self.user_json).get('data')
      if data:
        return data.get('name') or data.get('username')

    return self.key.string_id()

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def get(self, *args, **kwargs):
    """Wraps requests.get() and adds the Bearer token header.
    """
    headers = kwargs.setdefault('headers', {})
    headers['Authorization'] = 'Bearer ' + self.access_token_str
    headers.setdefault('User-Agent', USER_AGENT)

    resp = util.requests_get(*args, **kwargs)
    try:
      resp.raise_for_status()
    except BaseException, e:
      util.interpret_http_exception(e)
      raise
    return resp


class StartHandler(handlers.StartHandler):
  """Starts Medium auth. Requests an auth code and expects a redirect back.
  """
  DEFAULT_SCOPE = 'basicProfile'

  def redirect_url(self, state=None):
    assert (appengine_config.MEDIUM_CLIENT_ID and
            appengine_config.MEDIUM_CLIENT_SECRET), (
      "Please fill in the medium_client_id and "
      "medium_client_secret files in your app's root directory.")
    return str(GET_AUTH_CODE_URL % {
      'client_id': appengine_config.MEDIUM_CLIENT_ID,
      'redirect_uri': urllib.quote_plus(self.to_url()),
      # Medium requires non-empty state
      'state': urllib.quote_plus(state if state else 'unused'),
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
        raise exc.HTTPBadRequest('Error: %s' % error)

    # extract auth code and request access token
    auth_code = util.get_required_param(self, 'code')
    data = {
      'code': auth_code,
      'client_id': appengine_config.MEDIUM_CLIENT_ID,
      'client_secret': appengine_config.MEDIUM_CLIENT_SECRET,
      # redirect_uri here must be the same in the oauth code request!
      # (the value here doesn't actually matter since it's requested server side.)
      'redirect_uri': self.request.path_url,
      'grant_type': 'authorization_code',
      }
    resp = util.requests_post(
      GET_ACCESS_TOKEN_URL, data=urllib.urlencode(data),
      headers={'User-Agent': USER_AGENT}).text
    logging.debug('Access token response: %s', resp)

    try:
      resp = json.loads(resp)
    except:
      logging.exception('Could not decode JSON')
      raise

    errors = resp.get('errors') or resp.get('error')
    if errors:
      logging.info('Errors: %s', errors)
      raise exc.HTTPBadRequest(errors[0].get('message'))

    # TODO: handle refresh token
    access_token = resp['access_token']
    user_json = MediumAuth(access_token_str=access_token).get(API_USER_URL).text
    id = json.loads(user_json)['data']['id']
    auth = MediumAuth(id=id, access_token_str=access_token, user_json=user_json)
    auth.put()

    self.finish(auth, state=self.request.get('state'))
