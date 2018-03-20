"""Flickr OAuth drop-in.

Uses oauthlib directly to authenticate and sign requests with OAuth
1.0 credentials. https://www.flickr.com/services/api/auth.oauth.html

Note that when users decline Flickr's OAuth prompt by clicking the Cancel
button, Flickr redirects them to its home page, *not* to us.
"""
from future.utils import native_str

import json
import logging
import oauthlib.oauth1
import urllib
import urllib2
import urlparse

import appengine_config
import flickr_auth
import handlers
import models
from webutil import util

from google.appengine.ext import ndb
from webob import exc


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
    return self.key.string_id()

  def access_token(self):
    """Returns the OAuth access token as a (string key, string secret) tuple.
    """
    return (self.token_key, self.token_secret)

  def _api(self):
    return oauthlib.oauth1.Client(
      appengine_config.FLICKR_APP_KEY,
      client_secret=appengine_config.FLICKR_APP_SECRET,
      resource_owner_key=self.token_key,
      resource_owner_secret=self.token_secret,
      signature_type=oauthlib.oauth1.SIGNATURE_TYPE_QUERY)

  def urlopen(self, url, **kwargs):
    return flickr_auth.signed_urlopen(
      url, self.token_key, self.token_secret, **kwargs)

  def call_api_method(self, method, params):
    return flickr_auth.call_api_method(
      method, params, self.token_key, self.token_secret)


class StartHandler(handlers.StartHandler):
  """Starts three-legged OAuth with Flickr.

  Fetches an OAuth request token, then redirects to Flickr's auth page to
  request an access token.
  """
  def redirect_url(self, state=None):
    assert (appengine_config.FLICKR_APP_KEY and
            appengine_config.FLICKR_APP_SECRET), (
      "Please fill in the flickr_app_key and flickr_app_secret files in "
      "your app's root directory.")

    client = oauthlib.oauth1.Client(
      appengine_config.FLICKR_APP_KEY,
      client_secret=appengine_config.FLICKR_APP_SECRET,
      # double-URL-encode state because Flickr URL-decodes the redirect URL
      # before redirecting to it, and JSON values may have ?s and &s. e.g. the
      # Bridgy WordPress plugin's redirect URL when using Bridgy's registration
      # API (https://brid.gy/about#registration-api) looks like:
      # /wp-admin/admin.php?page=bridgy_options&service=flickr
      callback_uri=native_str(self.to_url(state=urllib.quote(state))))

    uri, headers, body = client.sign(REQUEST_TOKEN_URL)
    resp = util.urlopen(urllib2.Request(uri, body, headers))
    parsed = dict(urlparse.parse_qs(resp.read()))

    resource_owner_key = parsed.get('oauth_token')[0]
    resource_owner_secret = parsed.get('oauth_token_secret')[0]

    models.OAuthRequestToken(
      id=resource_owner_key,
      token_secret=resource_owner_secret,
      state=state).put()

    if self.scope:
      auth_url = AUTHORIZE_URL + '?' + urllib.urlencode({
        'perms': self.scope or 'read',
        'oauth_token': resource_owner_key
      })
    else:
      auth_url = AUTHENTICATE_URL + '?' + urllib.urlencode({
        'oauth_token': resource_owner_key
      })

    logging.info(
      'Generated request token, redirect to Flickr authorization url: %s',
      auth_url)
    return auth_url


class CallbackHandler(handlers.CallbackHandler):
  """The OAuth callback. Fetches an access token and redirects to the
  front page.
  """
  def get(self):
    oauth_token = self.request.get('oauth_token')
    oauth_verifier = self.request.get('oauth_verifier')
    request_token = models.OAuthRequestToken.get_by_id(oauth_token)

    client = oauthlib.oauth1.Client(
      appengine_config.FLICKR_APP_KEY,
      client_secret=appengine_config.FLICKR_APP_SECRET,
      resource_owner_key=oauth_token,
      resource_owner_secret=request_token.token_secret,
      verifier=oauth_verifier)

    uri, headers, body = client.sign(ACCESS_TOKEN_URL)
    try:
      resp = util.urlopen(urllib2.Request(uri, body, headers))
    except BaseException, e:
      util.interpret_http_exception(e)
      raise
    parsed = dict(urlparse.parse_qs(resp.read()))
    access_token = parsed.get('oauth_token')[0]
    access_secret = parsed.get('oauth_token_secret')[0]
    user_nsid = parsed.get('user_nsid')[0]

    if access_token is None:
      raise exc.HTTPBadRequest('Missing required query parameter oauth_token.')

    flickr_auth = FlickrAuth(id=user_nsid,
                             token_key=access_token,
                             token_secret=access_secret)
    user_json = flickr_auth.call_api_method('flickr.people.getInfo',
                                            {'user_id': user_nsid})

    flickr_auth.user_json = json.dumps(user_json)
    flickr_auth.put()

    self.finish(flickr_auth, state=self.request.get('state'))
