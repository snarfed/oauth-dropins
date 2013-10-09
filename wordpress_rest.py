"""WordPress.com OAuth drop-in.

Note that unlike Blogger and Tumblr, WordPress.com's OAuth tokens are *per
blog*. It asks you which blog to use on its authorization page.
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
  """Datastore model class for a WordPress blog accessed via REST API.

  The key name is the blog hostname.
  """
  blog_id = db.StringProperty(required=True)
  oauth_token = db.StringProperty(required=True)
  oauth_token_secret = db.StringProperty(required=True)


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
    logging.info('@ %s', resp)
    try:
      resp = json.loads(resp)
      blog_id = resp['blog_id']
      blog_url = resp['blog_url']
    except:
      logging.error('Bad JSON response: %r', self.request.params)
      raise

    token_key=self.request.get('oauth_token')
    token_secret= self.request.get('oauth_token_secret')
    WordPressAuth(key_name=util.domain_from_link(blog_url), blog_id=blog_id,
                  token_key=token_key, token_secret=token_secret).save()

    self.redirect('/?%s' % urllib.urlencode(
        {'wordpress_id': user_id,
         'wordpress_token_key': util.ellipsize(token_key),
         'wordpress_token_secret': util.ellipsize(token_secret),
         }))


application = webapp2.WSGIApplication([
    ('/wordpress_rest/start', StartHandler),
    (CALLBACK_PATH, oauth.callback_handler()),
    ], debug=appengine_config.DEBUG)
