"""Flickr OAuth drop-in.

Uses oauthlib directly to authenticate and sign requests with OAuth
1.0 credentials. https://www.flickr.com/services/api/auth.oauth.html

Note that when users decline Flickr's OAuth prompt by clicking the Cancel
button, Flickr redirects them to its home page, *not* to us.
"""
import logging
import oauthlib.oauth1
import urllib.parse, urllib.request

from flask import request
from google.cloud import ndb

from . import flickr_auth, views, models
from .webutil import flask_util, util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

REQUEST_TOKEN_URL = 'https://www.flickr.com/services/oauth/request_token'
AUTHORIZE_URL = 'https://www.flickr.com/services/oauth/authorize'
AUTHENTICATE_URL = 'https://www.flickr.com/services/oauth/authenticate'
ACCESS_TOKEN_URL = 'https://www.flickr.com/services/oauth/access_token'
API_URL = 'https://api.flickr.com/services/rest'


class FlickrAuth(models.BaseAuth):
  """An authenticated Flickr user.

  Provides methods that return information about this user and make
  OAuth-signed requests to the Flickr API. Stores OAuth credentials in
  the datastore. Key is the Flickr user ID. See models.BaseAuth for
  usage details.
  """
  # access token
  token_key = ndb.StringProperty(required=True)
  token_secret = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Flickr'

  def user_display_name(self):
    """Returns the user id.
    """
    return self.key_id()

  def access_token(self):
    """Returns the OAuth access token as a (string key, string secret) tuple.
    """
    return (self.token_key, self.token_secret)

  def _api(self):
    return oauthlib.oauth1.Client(
      flickr_auth.FLICKR_APP_KEY,
      client_secret=flickr_auth.FLICKR_APP_SECRET,
      resource_owner_key=self.token_key,
      resource_owner_secret=self.token_secret,
      signature_type=oauthlib.oauth1.SIGNATURE_TYPE_QUERY)

  def urlopen(self, url, **kwargs):
    return flickr_auth.signed_urlopen(
      url, self.token_key, self.token_secret, **kwargs)

  def call_api_method(self, method, params):
    return flickr_auth.call_api_method(
      method, params, self.token_key, self.token_secret)


class Start(views.Start):
  """Starts three-legged OAuth with Flickr.

  Fetches an OAuth request token, then redirects to Flickr's auth page to
  request an access token.
  """
  NAME = 'flickr'
  LABEL = 'Flickr'

  def redirect_url(self, state=None):
    assert flickr_auth.FLICKR_APP_KEY and flickr_auth.FLICKR_APP_SECRET, \
      "Please fill in the flickr_app_key and flickr_app_secret files in your app's root directory."

    # double-URL-encode state because Flickr URL-decodes the redirect URL before
    # redirecting to it, and JSON values may have ?s and &s. e.g. the Bridgy
    # WordPress plugin's redirect URL when using Bridgy's registration API
    # (https://brid.gy/about#registration-api) looks like:
    # /wp-admin/admin.php?page=bridgy_options&service=flickr
    if state:
      state = urllib.parse.quote(state)

    client = oauthlib.oauth1.Client(
      flickr_auth.FLICKR_APP_KEY,
      client_secret=flickr_auth.FLICKR_APP_SECRET,
      callback_uri=self.to_url(state))

    url, headers, data = client.sign(REQUEST_TOKEN_URL)
    resp = util.requests_get(url, headers=headers, data=data)
    resp.raise_for_status()
    parsed = urllib.parse.parse_qs(resp.text)
    logger.info(f'Got {parsed}')

    if parsed.get('error') or parsed.get('oauth_problem'):
      flask_util.error(resp.text)

    resource_owner_key = parsed.get('oauth_token')
    resource_owner_secret = parsed.get('oauth_token_secret')
    if not resource_owner_key or not resource_owner_secret:
      flask_util.error(f'Unexpected Flickr error: {resp.text}')

    models.OAuthRequestToken(
      id=resource_owner_key[0],
      token_secret=resource_owner_secret[0],
      state=state).put()

    if self.scope:
      auth_url = AUTHORIZE_URL + '?' + urllib.parse.urlencode({
        'perms': self.scope or 'read',
        'oauth_token': resource_owner_key[0],
      })
    else:
      auth_url = AUTHENTICATE_URL + '?' + urllib.parse.urlencode({
        'oauth_token': resource_owner_key[0],
      })

    logger.info(
      'Generated request token, redirect to Flickr authorization url: %s',
      auth_url)
    return auth_url

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args, input_style='background-color: #EEEEEE; padding: 10px', **kwargs)


class Callback(views.Callback):
  """The OAuth callback. Fetches an access token and redirects to the
  front page.
  """
  def dispatch_request(self):
    oauth_token = request.values.get('oauth_token')
    oauth_verifier = request.values.get('oauth_verifier')
    request_token = models.OAuthRequestToken.get_by_id(oauth_token)

    client = oauthlib.oauth1.Client(
      flickr_auth.FLICKR_APP_KEY,
      client_secret=flickr_auth.FLICKR_APP_SECRET,
      resource_owner_key=oauth_token,
      resource_owner_secret=request_token.token_secret,
      verifier=oauth_verifier)

    uri, headers, body = client.sign(ACCESS_TOKEN_URL)
    try:
      resp = util.urlopen(urllib.request.Request(uri, body, headers))
    except BaseException as e:
      util.interpret_http_exception(e)
      raise
    parsed = dict(urllib.parse.parse_qs(resp.read().decode()))
    access_token = parsed.get('oauth_token')[0]
    access_secret = parsed.get('oauth_token_secret')[0]
    user_nsid = parsed.get('user_nsid')[0]

    if access_token is None:
      flask_util.error('Missing required query parameter oauth_token.')

    auth = FlickrAuth(id=user_nsid, token_key=access_token,
                      token_secret=access_secret)
    user_json = auth.call_api_method('flickr.people.getInfo', {'user_id': user_nsid})

    auth.user_json = json_dumps(user_json)
    auth.put()

    return self.finish(auth, state=request.values.get('state'))
