"""Facebook OAuth drop-in.

TODO: implement client state param
TODO: unify this with instagram. see file docstring comment there.
"""

import json
import logging
import urllib
import urllib2
import urlparse
from webob import exc

import appengine_config
from appengine_config import HTTP_TIMEOUT
import handlers
import models
from webutil import util

from google.appengine.ext import ndb
import webapp2


# facebook api url templates. can't (easily) use urllib.urlencode() because i
# want to keep the %(...)s placeholders as is and fill them in later in code.
GET_AUTH_CODE_URL = str('&'.join((
    'https://www.facebook.com/dialog/oauth?'
    # https://developers.facebook.com/docs/reference/login/
    'scope=%(scope)s',
    'client_id=%(client_id)s',
    # redirect_uri here must be the same in the access token request!
    'redirect_uri=%(redirect_uri)s',
    'response_type=code',
    )))
GET_ACCESS_TOKEN_URL = str('&'.join((
    'https://graph.facebook.com/oauth/access_token?'
    'client_id=%(client_id)s',
    # redirect_uri here must be the same in the oauth request!
    # (the value here doesn't actually matter since it's requested server side.)
    'redirect_uri=%(redirect_uri)s',
    'client_secret=%(client_secret)s',
    'code=%(auth_code)s',
    )))
API_USER_URL = 'https://graph.facebook.com/me'


class FacebookAuth(models.BaseAuth):
  """An authenticated Facebook user or page.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to Facebook's HTTP-based APIs. Stores OAuth credentials
  in the datastore. See models.BaseAuth for usage details.

  Facebook-specific details: implements urlopen() but not http() or api(). The
  key name is the user's or page's Facebook ID.
  """
  auth_code = ndb.StringProperty(required=True)
  access_token_str = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Facebook'

  def user_display_name(self):
    """Returns the user's or page's name.
    """
    return json.loads(self.user_json)['name']

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds OAuth credentials to the request.
    """
    return models.BaseAuth.urlopen_access_token(url, self.access_token_str,
                                                **kwargs)


class StartHandler(handlers.StartHandler):
  """Starts Facebook auth. Requests an auth code and expects a redirect back.
  """

  def redirect_url(self, state=None):
    assert (appengine_config.FACEBOOK_APP_ID and
            appengine_config.FACEBOOK_APP_SECRET), (
      "Please fill in the facebook_app_id and facebook_app_secret files in "
      "your app's root directory.")
    return str(GET_AUTH_CODE_URL % {
      'client_id': appengine_config.FACEBOOK_APP_ID,
      'scope': self.scope,
      # TODO: CSRF protection identifier.
      # http://developers.facebook.com/docs/authentication/
      'redirect_uri': urllib.quote_plus(self.to_url(state=state)),
      })


class CallbackHandler(handlers.CallbackHandler):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """

  def get(self):
    if CallbackHandler.handle_error(self):
      return

    auth_code = self.request.get('code')
    assert auth_code

    url = GET_ACCESS_TOKEN_URL % {
      'auth_code': auth_code,
      'client_id': appengine_config.FACEBOOK_APP_ID,
      'client_secret': appengine_config.FACEBOOK_APP_SECRET,
      'redirect_uri': urllib.quote_plus(self.request_url_with_state()),
      }
    logging.debug('Fetching: %s', url)
    resp = urllib2.urlopen(url, timeout=HTTP_TIMEOUT).read()
    logging.debug('Access token response: %s', resp)
    params = urlparse.parse_qs(resp)
    access_token = params['access_token'][0]

    resp = models.BaseAuth.urlopen_access_token(API_USER_URL, access_token).read()
    logging.debug('User info response: %s', resp)
    user_id = json.loads(resp)['id']

    auth = FacebookAuth(id=user_id,
                        user_json=resp,
                        auth_code=auth_code,
                        access_token_str=access_token)
    auth.put()
    self.finish(auth, state=self.request.get('state'))

  @staticmethod
  def handle_error(handler):
    """Handles any error reported in the callback query parameters.

    Args:
      handler: CallbackHandler

    Returns: True if there was an error, False otherwise.
    """
    error = handler.request.get('error')
    error_reason = handler.request.get('error_reason')

    if error or error_reason:
      error_description = urllib.unquote_plus(
        handler.request.get('error_description', ''))
      if error == 'access_denied' and error_reason == 'user_denied':
        logging.info('User declined: %s', error_description)
        handler.finish(None, state=handler.request.get('state'))
        return True
      else:
        raise exc.HTTPBadRequest(' '.join((error, error_reason, error_description)))

    return False
