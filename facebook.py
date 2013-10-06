"""Facebook OAuth drop-in.
"""

import json
import logging
import urllib
import urllib2
import urlparse

import appengine_config
from webutil import handlers
from webutil import models
from webutil import util

from google.appengine.ext import db
import webapp2

# facebook api url templates. can't (easily) use urllib.urlencode() because i
# want to keep the %(...)s placeholders as is and fill them in later in code.
GET_AUTH_CODE_URL = str('&'.join((
    'https://www.facebook.com/dialog/oauth?',
    # https://developers.facebook.com/docs/reference/login/
    'scope=offline_access',
    'client_id=%(client_id)s',
    # redirect_uri here must be the same in the access token request!
    'redirect_uri=%(host_url)s/facebook/auth_callback',
    'response_type=code',
    'state=foo',
    )))

GET_ACCESS_TOKEN_URL = str('&'.join((
    'https://graph.facebook.com/oauth/access_token?'
    'client_id=%(client_id)s',
    # redirect_uri here must be the same in the oauth request!
    # (the value here doesn't actually matter since it's requested server side.)
    'redirect_uri=%(host_url)s/facebook/auth_callback',
    'client_secret=%(client_secret)s',
    'code=%(auth_code)s',
    )))

API_USER_URL = 'https://graph.facebook.com/me?access_token=%s'


class FacebookAuth(models.KeyNameModel):
  """Datastore model class for a Facebook auth code and access token.

  The key name is the user's or page's Facebook ID.
  """
  auth_code = db.StringProperty(required=True)
  access_token = db.StringProperty(required=True)
  info_json = db.TextProperty(required=True)


class StartHandler(webapp2.RequestHandler):
  """Starts Facebook auth. Requests an auth code and expects a redirect back.
  """
  handle_exception = handlers.handle_exception

  def post(self):
    url = GET_AUTH_CODE_URL % {
      'client_id': appengine_config.FACEBOOK_APP_ID,
      # TODO: CSRF protection identifier.
      # http://developers.facebook.com/docs/authentication/
      'host_url': self.request.host_url,
      }
    logging.debug('Redirecting to: %s', url)
    self.redirect(str(url))


class CallbackHandler(webapp2.RequestHandler):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """
  handle_exception = handlers.handle_exception

  def get(self):
    auth_code = self.request.get('code')
    assert auth_code

    # TODO: handle permission declines, errors, etc
    url = GET_ACCESS_TOKEN_URL % {
      'auth_code': auth_code,
      'client_id': appengine_config.FACEBOOK_APP_ID,
      'client_secret': appengine_config.FACEBOOK_APP_SECRET,
      'host_url': self.request.host_url,
      }
    logging.debug('Fetching: %s', url)
    resp = urllib2.urlopen(url).read()
    logging.debug('Access token response: %s', resp)
    params = urlparse.parse_qs(resp)
    access_token = params['access_token'][0]

    url = API_USER_URL % access_token
    logging.debug('Fetching: %s', url)
    resp = urllib2.urlopen(url).read()
    logging.debug('User info response: %s', resp)
    user_id = json.loads(resp)['id']

    FacebookAuth.get_or_insert(key_name=user_id, info_json=resp,
                               auth_code=auth_code, access_token=access_token).save()
    self.redirect('/?%s' % urllib.urlencode(
        {'facebook_id': user_id,
         'facebook_auth_code': util.ellipsize(auth_code),
         'facebook_access_token': util.ellipsize(access_token),
         }))


application = webapp2.WSGIApplication([
    ('/facebook/start', StartHandler),
    ('/facebook/auth_callback', CallbackHandler),
    ], debug=appengine_config.DEBUG)
