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
from urllib.parse import quote_plus, unquote, urlencode, urljoin, urlparse, urlunparse

from google.cloud import ndb
import requests
from webob import exc

from . import handlers
from .models import BaseAuth
from .webutil import appengine_info, util
from .webutil.util import json_dumps, json_loads

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

INSTANCE_API = '/api/v1/instance'
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


def _encode_state(app, state):
  wrapped = json_dumps({
    'app_key': app.key.urlsafe().decode(),
    'state': quote_plus(state),
  })
  logging.debug('Encoding wrapper state: %r', wrapped)
  return wrapped


def _decode_state(state):
  logging.debug('Decoding wrapper state: %r', state)
  decoded = json_loads(state)
  return decoded['app_key'], unquote(decoded['state'])


class MastodonApp(ndb.Model):
  """A Mastodon API OAuth2 app registered with a specific instance."""
  instance = ndb.StringProperty(required=True)  # URL, eg https://mastodon.social/
  data = ndb.TextProperty(required=True)  # JSON; includes client id/secret
  instance_info = ndb.TextProperty()  # JSON; from /api/v1/instance
  app_url = ndb.StringProperty()
  app_name = ndb.StringProperty()
  created_at = ndb.DateTimeProperty(auto_now_add=True, required=True)


class MastodonAuth(BaseAuth):
  """An authenticated Mastodon user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the Mastodon REST API. Stores OAuth credentials in the datastore.
  See models.BaseAuth for usage details.

  Key name is the fully qualified actor address, ie @username@instance.tld.

  Implements get() and post() but not urlopen() or api().
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

  def user_id(self):
    """Returns the user's id, eg 123."""
    return json_loads(self.user_json).get('id')

  def access_token(self):
    """Returns the OAuth access token string."""
    return self.access_token_str

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


class StartHandler(handlers.StartHandler):
  """Starts Mastodon auth. Requests an auth code and expects a redirect back.

  Attributes:
    DEFAULT_SCOPE: string, default OAuth scope(s) to request
    REDIRECT_PATHS: sequence of string URL paths (on this host) to register as
      OAuth callback (aka redirect) URIs in the OAuth app
    SCOPE_SEPARATOR: string, used to separate multiple scopes
  """
  NAME = 'mastodon'
  LABEL = 'Mastodon'
  DEFAULT_SCOPE = 'read:accounts'
  REDIRECT_PATHS = ()
  SCOPE_SEPARATOR = ' '

  @classmethod
  def to(cls, path, **kwargs):
    return super(StartHandler, cls).to(path, **kwargs)

  def app_name(self):
    """Returns the user-visible name of this application.

    To be overridden by subclasses. Displayed in Mastodon's OAuth prompt.
    """
    return 'oauth-dropins demo'

  def app_url(self):
    """Returns this application's web site.

    To be overridden by subclasses. Displayed in Mastodon's OAuth prompt.
    """
    return self.request.host_url

  def redirect_url(self, state=None, instance=None):
    """Returns the local URL for Mastodon to redirect back to after OAuth prompt.

    Args:
      state: string, user-provided value to be returned as a query parameter in
        the return redirect
      instance: string, Mastodon instance base URL, e.g.
        'https://mastodon.social'. May also be provided in the 'instance'
        request as a URL query parameter or POST body.

    Raises: ValueError if instance isn't a Mastodon instance.
    """
    # normalize instance to URL
    if not instance:
      instance = util.get_required_param(self, 'instance')
    instance = instance.strip().split('@')[-1]  # handle addresses, eg user@host.com
    parsed = urlparse(instance)
    if not parsed.scheme:
      instance = 'https://' + instance

    # fetch instance info from this instance's API (mostly to test that it's
    # actually a Mastodon instance)
    try:
      resp = util.requests_get(urljoin(instance, INSTANCE_API))
    except requests.RequestException as e:
      logging.info('Error', stack_info=True)
      resp = None

    is_json = resp and resp.headers.get('Content-Type', '').strip().startswith(
      'application/json')
    if is_json:
      logging.info(resp.text)
    if (not resp or not resp.ok or not is_json or
        # Pixelfed (https://pixelfed.org/) pretends to be Mastodon but isn't
        'Pixelfed' in resp.json().get('version')):
      msg = "%s doesn't look like a Mastodon instance." % instance
      logging.info(resp)
      logging.info(msg)
      raise ValueError(msg)

    # if we got redirected, update instance URL
    parsed = list(urlparse(resp.url))
    parsed[2] = '/'  # path
    instance = urlunparse(parsed)

    app_name = self.app_name()
    app_url = self.app_url()
    query = MastodonApp.query(MastodonApp.instance == instance,
                              MastodonApp.app_url == app_url)
    if appengine_info.DEBUG:
      # disambiguate different apps in dev_appserver, since their app_url will
      # always be localhost
      query = query.filter(MastodonApp.app_name == app_name)
    app = query.get()
    if not app:
      app = self._register_app(instance, app_name, app_url)
      app.instance_info = resp.text
      app.put()

    logging.info('Starting OAuth for Mastodon instance %s', instance)
    app_data = json_loads(app.data)
    return urljoin(instance, AUTH_CODE_API % {
      'client_id': app_data['client_id'],
      'client_secret': app_data['client_secret'],
      'redirect_uri': quote_plus(self.to_url()),
      'state': _encode_state(app, state),
      'scope': self.scope,
    })

  def _register_app(self, instance, app_name, app_url):
    """Register a Mastodon API app on a specific instance.

    https://docs.joinmastodon.org/api/rest/apps/

    Args:
      instance: string
      app_name: string
      app_url: string

    Returns: MastodonApp
    """
    logging.info("first time we've seen Mastodon instance %s with app %s %s! "
                 "registering an API app.", instance, app_name, app_url)

    redirect_uris = set(urljoin(self.request.host_url, path)
                        for path in set(self.REDIRECT_PATHS))
    redirect_uris.add(self.to_url())

    resp = util.requests_post(
      urljoin(instance, REGISTER_APP_API),
      data=urlencode({
        'client_name': app_name,
        # Mastodon uses Doorkeeper for OAuth, which allows registering
        # multiple redirect URIs, separated by newlines.
        # https://github.com/doorkeeper-gem/doorkeeper/pull/298
        # https://docs.joinmastodon.org/api/rest/apps/
        'redirect_uris': '\n'.join(redirect_uris),
        'website': app_url,
        # https://docs.joinmastodon.org/api/permissions/
        'scopes': self.SCOPE_SEPARATOR.join(ALL_SCOPES),
      }))
    resp.raise_for_status()

    app_data = json_loads(resp.text)
    logging.info('Got %s', app_data)
    app = MastodonApp(instance=instance, app_name=app_name,
                      app_url=app_url, data=json_dumps(app_data))
    app.put()
    return app

  @classmethod
  def button_html(cls, *args, **kwargs):
    kwargs['form_extra'] = kwargs.get('form_extra', '') + """
<input type="url" name="instance" class="form-control" placeholder="Mastodon instance" scheme="https" required style="width: 150px; height: 50px; display:inline;" />"""
    return super(cls, cls).button_html(
      *args, input_style='background-color: #EBEBEB; padding: 5px', **kwargs)


class CallbackHandler(handlers.CallbackHandler):
  """The OAuth callback. Fetches an access token and stores it."""
  def get(self):
    app_key, state = _decode_state(util.get_required_param(self, 'state'))

    # handle errors
    error = self.request.get('error')
    desc = self.request.get('error_description')
    if error:
      # user_cancelled_login and user_cancelled_authorize are non-standard.
      # https://tools.ietf.org/html/rfc6749#section-4.1.2.1
      if error in ('user_cancelled_login', 'user_cancelled_authorize', 'access_denied'):
        logging.info('User declined: %s', self.request.get('error_description'))
        self.finish(None, state=state)
        return
      else:
        msg = 'Error: %s: %s' % (error, desc)
        logging.info(msg)
        raise exc.HTTPBadRequest(msg)

    app = ndb.Key(urlsafe=app_key).get()
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
    resp = util.requests_post(urljoin(app.instance, ACCESS_TOKEN_API),
                              data=urlencode(data))
    resp.raise_for_status()
    resp_json = resp.json()
    logging.debug('Access token response: %s', resp_json)
    if resp_json.get('error'):
      raise exc.HTTPBadRequest(resp_json)

    access_token = resp_json['access_token']
    user = MastodonAuth(app=app.key, access_token_str=access_token).get(VERIFY_API).json()
    logging.debug('User: %s', user)
    address = '@%s@%s' % (user['username'], urlparse(app.instance).netloc)
    auth = MastodonAuth(id=address, app=app.key, access_token_str=access_token,
                        user_json=json_dumps(user))
    auth.put()

    self.finish(auth, state=state)
