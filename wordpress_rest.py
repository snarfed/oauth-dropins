"""WordPress.com OAuth drop-in.

API docs:
https://developer.wordpress.com/docs/api/
https://developer.wordpress.com/docs/oauth2/

Note that unlike Blogger and Tumblr, WordPress.com's OAuth tokens are *per
blog*. It asks you which blog to use on its authorization page.

TODO(ryan): this breaks when the user is already connected and tries to
reconnect, ie hits the /wordpress_rest/start_handler again. Clearing the
datastore fixes it, but we should handle it without that.
"""

import json
import logging
import urllib

import appengine_config
from oauth2client.appengine import OAuth2Decorator
from webutil import handlers
from webutil import util

from google.appengine.ext import db
import webapp2


TOKEN_RESPONSE_PARAM = 'token_response'

CALLBACK_PATH = '/wordpress_rest/oauth_callback'
oauth = OAuth2Decorator(
  client_id=appengine_config.WORDPRESS_CLIENT_ID,
  client_secret=appengine_config.WORDPRESS_CLIENT_SECRET,
  # can't find any mention of oauth scope in https://developer.wordpress.com/
  scope='',
  auth_uri='https://public-api.wordpress.com/oauth2/authorize',
  token_uri='https://public-api.wordpress.com/oauth2/token',
  # wordpress.com doesn't let you use an oauth redirect URL with "local" or
  # "localhost" anywhere in it. :/ had to use my.dev.com and put this in
  # /etc/hosts:   127.0.0.1 my.dev.com
  callback_path=('http://my.dev.com:8080' if appengine_config.DEBUG else '') +
    CALLBACK_PATH,
  # the HTTP request that gets an access token also gets the blog id and
  # url selected by the user, so grab it from the token response.
  token_response_param=TOKEN_RESPONSE_PARAM)


class WordPressAuth(db.Model):
  """An authenticated WordPress user or page.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to the WordPress REST API. Stores OAuth credentials in
  the datastore. See models.BaseAuth for usage details.

  WordPress-specific details: implements urlopen() but not http() or api(). The
  key name is the blog hostname.
  """
  blog_id = db.StringProperty(required=True)
  access_token = db.StringProperty(required=True)

  def site_name(self):
    return 'WordPress'

  def user_display_name(self):
    """Returns the blog hostname.
    """
    return self.key().name()

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds OAuth credentials to the request.
    """
    return BaseAuth.urlopen_access_token(url, self.access_token, **kwargs)


class StartHandler(webapp2.RequestHandler):
  handle_exception = handlers.handle_exception

  @oauth.oauth_required
  def post(self):
    self.get()

  @oauth.oauth_required
  def get(self):
    # the HTTP request that gets an access token also gets the blog id and
    # url selected by the user, so grab it from the token response.
    # https://developer.wordpress.com/docs/oauth2/#exchange-code-for-access-token
    resp = self.request.get(TOKEN_RESPONSE_PARAM)
    logging.debug('Access token response: %r', resp)
    try:
      resp = json.loads(resp)
      blog_id = resp['blog_id']
      blog_domain = util.domain_from_link(resp['blog_url'])
      access_token = resp['access_token']
    except:
      logging.exception('Could not decode JSON')
      raise

    key = WordPressAuth(key_name=blog_domain,
                        blog_id=blog_id,
                        access_token=access_token).save()
    self.redirect('/?entity_key=%s' % key)


application = webapp2.WSGIApplication([
    ('/wordpress_rest/start', StartHandler),
    (CALLBACK_PATH, oauth.callback_handler()),
    ], debug=appengine_config.DEBUG)
