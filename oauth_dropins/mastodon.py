"""Mastodon OAuth drop-in.

Mastodon is an ActivityPub implementation, but it also has a REST + OAuth 2 API
independent of AP. Uh, ok, sure.

API docs: https://docs.joinmastodon.org/api/

Interestingly: as usual w/OAuth, they require registering apps beforehand...but
since AP and Mastodon are decentralized, there's no single place to register an
app. So they have an API for registering apps, per instance:
https://docs.joinmastodon.org/api/authentication/
Surprising, and unusual, but makes sense.
"""
import logging
import urllib
import urlparse

import appengine_config
from google.appengine.ext import ndb
from webob import exc
from webutil import util
from webutil.util import json_dumps, json_loads

import handlers
from models import BaseAuth

# https://docs.joinmastodon.org/api/permissions/
ALL_SCOPES = (
  'read',
  'read:accounts',
  'read:blocks',
  'read:favourites',
  'read:filters',
  'read:follows',
  'read:lists',
  'read:mutes',
  'read:notifications',
  'read:reports',
  'read:search',
  'read:statuses',
  'write',
  'write:accounts',
  'write:blocks',
  'write:favourites',
  'write:filters',
  'write:follows',
  'write:lists',
  'write:media',
  'write:mutes',
  'write:notifications',
  'write:reports',
  'write:statuses',
  'follow',
  'push',
)

REGISTER_APP_API = '/api/v1/apps'
VERIFY_API = '/api/v1/accounts/verify_credentials'

# URL templates. Can't (easily) use urlencode() because I want to keep
# the %(...)s placeholders as is and fill them in later in code.
AUTH_CODE_API = '&'.join((
    '/oauth/authorize?'
    'response_type=code',
    'client_id=%(client_id)s',
    'client_secret=%(client_secret)s',
    # https://docs.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api?context=linkedin/consumer/context#permissions
    'scope=%(scope)s',
    # must be the same in the access token request
    'redirect_uri=%(redirect_uri)s',
    'state=%(state)s',
    ))

ACCESS_TOKEN_API = '/oauth/token'


class MastodonApp(ndb.Model):
  """A Mastodon API OAuth2 app registered with a specific instance."""
  instance = ndb.StringProperty(required=True)  # URL, eg https://mastodon.social/
  data = ndb.TextProperty(required=True)  # includes client_id and client_secret
  created_at = ndb.DateTimeProperty(auto_now_add=True, required=True)


class MastodonAuth(BaseAuth):
  """An authenticated Mastodon user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the Mastodon REST API. Stores OAuth credentials in the datastore.
  See models.BaseAuth for usage details.

  Key name is the fully qualified actor address, ie @username@instance.tld.

  Implements get() and post() but not urlopen(), http(), or api().
  """
  app = ndb.KeyProperty()
  access_token_str = ndb.TextProperty(required=True)
  user_json = ndb.TextProperty()

  def site_name(self):
    return 'Mastodon'

  def user_display_name(self):
    """Returns the user's full ActivityPub address, eg @ryan@mastodon.social."""
    return self.key.id()

  def instance(self):
    """Returns the instance base URL, eg https://mastodon.social/."""
    return self.app.get().instance

  def username(self):
    """Returns the user's username, eg ryan."""
    return json_loads(self.user_json).get('username')

  def access_token(self):
    """Returns the OAuth access token string."""
    return self.access_token_str

  def get(self, *args, **kwargs):
    """Wraps requests.get() and adds instance base URL and Bearer token header."""
    url = urlparse.urljoin(self.instance(), args[0])
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
    except BaseException, e:
      util.interpret_http_exception(e)
      raise
    return resp


class StartHandler(handlers.StartHandler):
  """Starts Mastodon auth. Requests an auth code and expects a redirect back.

  Attributes:
    APP_NAME: string, user-visible name of this application. Displayed in Mastodon's
      OAuth prompt.
    APP_URL: string, this application's web site

  Args:
    instance: string, base URL of the Mastodon instance, eg 'https://mastodon.social/'
  """
  APP_NAME = 'oauth-dropins demo'
  APP_URL = 'https://oauth-dropins.appspot.com/'
  DEFAULT_SCOPE = 'read:accounts'
  SCOPE_SEPARATOR = ' '

  @classmethod
  def to(cls, path, app_name=None, app_url=None, **kwargs):
    if app_name is not None:
      cls.APP_NAME = app_name
    if app_url is not None:
      cls.APP_URL = app_url
    return super(cls, cls).to(path, **kwargs)

  def redirect_url(self, state=None, instance=None):
    # TODO
    assert not state

    # TODO: unify with indieauth?
    if not instance:
      instance = util.get_required_param(self, 'instance')
    parsed = urlparse.urlparse(instance)
    if not parsed.scheme:
      instance = 'https://' + instance

    callback_url = self.to_url()

    app = MastodonApp.query(MastodonApp.instance == instance).get()
    if app:
      app_data = json_loads(app.data)
    else:
      # register an API app!
      # https://docs.joinmastodon.org/api/rest/apps/
      logging.info("first time we've seen instance %s! registering an API app now.", instance)
      resp = util.requests_post(
        urlparse.urljoin(instance, REGISTER_APP_API),
        data=urllib.urlencode({
          'client_name': self.APP_NAME,
          'redirect_uris': callback_url,
          'website': self.APP_URL,
          # https://docs.joinmastodon.org/api/permissions/
          'scopes': self.SCOPE_SEPARATOR.join(ALL_SCOPES),
        }))
      resp.raise_for_status()
      app_data = json_loads(resp.text)
      logging.info('Got %s', app_data)
      app = MastodonApp(instance=instance, data=json_dumps(app_data))
      app.put()

    return urlparse.urljoin(instance, AUTH_CODE_API % {
      'client_id': app_data['client_id'],
      'client_secret': app_data['client_secret'],
      'redirect_uri': urllib.quote_plus(callback_url),
      'state': urllib.quote_plus(instance),
      'scope': self.scope,
      })


class CallbackHandler(handlers.CallbackHandler):
  """The OAuth callback. Fetches an access token and stores it."""
  def get(self):
    instance = self.request.get('state')

    # handle errors
    error = self.request.get('error')
    desc = self.request.get('error_description')
    if error:
      # TODO: doc link
      if error in ('user_cancelled_login', 'user_cancelled_authorize', 'access_denied'):
        logging.info('User declined: %s', self.request.get('error_description'))
        self.finish(None, state=instance)
        return
      else:
        msg = 'Error: %s: %s' % (error, desc)
        logging.info(msg)
        raise exc.HTTPBadRequest(msg)


    app = MastodonApp.query(MastodonApp.instance == instance).get()
    assert app
    app_data = json_loads(app.data)

    # extract auth code and request access token
    auth_code = util.get_required_param(self, 'code')
    data = {
      'grant_type': 'authorization_code',
      'code': auth_code,
      'client_id': app_data['client_id'],
      'client_secret': app_data['client_secret'],
      # redirect_uri here must be the same in the oauth code request!
      # (the value here doesn't actually matter since it's requested server side.)
      'redirect_uri': self.request.path_url,
      }
    resp = util.requests_post(urlparse.urljoin(instance, ACCESS_TOKEN_API),
                              data=urllib.urlencode(data))
    resp.raise_for_status()
    resp_json = resp.json()
    logging.debug('Access token response: %s', resp_json)
    if resp_json.get('error'):
      raise exc.HTTPBadRequest(resp_json)

    access_token = resp_json['access_token']
    user = MastodonAuth(app=app.key, access_token_str=access_token).get(VERIFY_API).json()
    logging.debug('User: %s', user)
    address = '@%s@%s' % (user['username'], urlparse.urlparse(instance).netloc)
    auth = MastodonAuth(id=address, app=app.key, access_token_str=access_token,
                        user_json=json_dumps(user))
    auth.put()

    self.finish(auth, state=self.request.get('state'))
