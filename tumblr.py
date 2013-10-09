"""Tumblr OAuth drop-in.

http://www.tumblr.com/docs/en/api/v2
"""

import json
import logging
import urllib
import urlparse

import appengine_config
import tumblpy
from webob import exc
from webutil import handlers
from webutil import models
from webutil import util

from google.appengine.ext import db
from google.appengine.ext.webapp import template
import webapp2


# http://www.tumblr.com/oauth/apps
OAUTH_CALLBACK_PATH = '/tumblr/oauth_callback'


class TumblrRequestToken(models.KeyNameModel):
  """Datastore model class for a Twitter OAuth request token.

  This is only intermediate data. Client should use TwitterOAuthToken instances
  to make Twitter API calls.

  The key name is the token key.
  """
  token_secret = db.StringProperty(required=True)


class TumblrAuth(models.KeyNameModel):
  """Datastore model class for a Tumblr blog.

  The key name is the username.
  """
  token_key = db.StringProperty(required=True)
  token_secret = db.StringProperty(required=True)
  info_json = db.TextProperty(required=True)


class StartHandler(webapp2.RequestHandler):
  """Starts Tumblr auth. Requests an auth code and expects a redirect back.
  """
  handle_exception = handlers.handle_exception

  def post(self):
    tp = tumblpy.Tumblpy(app_key=appengine_config.TUMBLR_APP_KEY,
                         app_secret=appengine_config.TUMBLR_APP_SECRET)
    auth_props = tp.get_authentication_tokens(
      callback_url=self.request.host_url + OAUTH_CALLBACK_PATH)

    # store the request token for later use in the callback handler
    TumblrRequestToken(key_name=auth_props['oauth_token'],
                       token_secret=auth_props['oauth_token_secret']).save()
    auth_url = auth_props['auth_url']
    logging.info('Generated request token, redirecting to Tumblr: %s', auth_url)
    self.redirect(auth_url)


class CallbackHandler(webapp2.RequestHandler):
  """OAuth callback. Fetches the user's blogs and re-renders the front page.
  """
  handle_exception = handlers.handle_exception

  def get(self):
    # lookup the request token
    request_token_key = self.request.get('oauth_token')
    request_token = TumblrRequestToken.get_by_key_name(request_token_key)
    if request_token is None:
      raise exc.HTTPBadRequest('Invalid oauth_token: %s' % request_token_key)

    # generate and store the final token
    tp = tumblpy.Tumblpy(app_key=appengine_config.TUMBLR_APP_KEY,
                         app_secret=appengine_config.TUMBLR_APP_SECRET,
                         oauth_token=request_token_key,
                         oauth_token_secret=request_token.token_secret)
    auth_token = tp.get_authorized_tokens(self.request.params['oauth_verifier'])
    auth_token_key = auth_token['oauth_token']
    auth_token_secret = auth_token['oauth_token_secret']

    # get the user's blogs
    # http://www.tumblr.com/docs/en/api/v2#user-methods
    tp = tumblpy.Tumblpy(app_key=appengine_config.TUMBLR_APP_KEY,
                         app_secret=appengine_config.TUMBLR_APP_SECRET,
                         oauth_token=auth_token_key,
                         oauth_token_secret=auth_token_secret)
    logging.info('Fetching user/info')
    resp = tp.post('user/info')
    logging.info('Got: %s', resp)
    user = resp['user']

    TumblrAuth(key_name=user['name'],
               token_key=auth_token_key,
               token_secret=auth_token_secret,
               info_json=json.dumps(resp)).save()

    hostnames = util.trim_nulls([util.domain_from_link(b['url'])
                                 for b in user['blogs']])
    self.redirect('/?%s' + urllib.urlencode({
          'tumblr_username': user['name'],
          'tumblr_hostnames': hostnames,
          'tumblr_token_key': util.ellipsize(auth_token_key),
          'tumblr_token_secret': util.ellipsize(auth_token_secret),
          }, True))


application = webapp2.WSGIApplication([
    ('/tumblr/start', StartHandler),
    (OAUTH_CALLBACK_PATH, CallbackHandler),
    ], debug=appengine_config.DEBUG)
