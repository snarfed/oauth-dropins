"""Blogger v2 GData API OAuth drop-in.

https://developers.google.com/blogger/docs/2.0/developers_guider

Uses google-api-python-client to auth via OAuth 2. This describes how to get
gdata-python-client to use an OAuth 2 token from google-api-python-client:
http://blog.bossylobster.com/2012/12/bridging-oauth-20-objects-between-gdata.html#comment-form

Support was added to gdata-python-client here:
https://code.google.com/p/gdata-python-client/source/detail?r=ecb1d49b5fbe05c9bc6c8525e18812ccc02badc0
"""

import logging
import urllib
import urlparse

import appengine_config
import models
from webutil import handlers
from webutil import models
from webutil import util

from oauth2client.appengine import OAuth2Decorator
from gdata.blogger import client
from gdata import gauth
from google.appengine.api import users
from google.appengine.ext import db
import webapp2


oauth = OAuth2Decorator(
  client_id=appengine_config.GOOGLE_CLIENT_ID,
  client_secret=appengine_config.GOOGLE_CLIENT_SECRET,
  # https://developers.google.com/blogger/docs/2.0/developers_guide_protocol#OAuth2Authorizing
  # (the scope for the v3 API is https://www.googleapis.com/auth/blogger)
  scope='http://www.blogger.com/feeds/',
  callback_path='/blogger_v2/oauth2callback')


class BloggerV2Auth(models.KeyNameModel):
  """A Blogger blog. The key name is the Blogger username."""
  hostnames = db.StringListProperty(required=True)
  creds_json = db.TextProperty(required=True)


class StartHandler(webapp2.RequestHandler):
  """Connects a Blogger account. Authenticates via OAuth if necessary."""
  @oauth.oauth_required
  def post(self):
    return self.get()

  @oauth.oauth_required
  def get(self):
    # this must be a client ie subclass of GDClient, since that's what
    # OAuth2TokenFromCredentials.authorize() expects, *not* a service ie
    # subclass of GDataService.
    blogger = client.BloggerClient()
    auth_token = gauth.OAuth2TokenFromCredentials(oauth.credentials)
    auth_token.authorize(blogger)

    # get the current user
    blogs = blogger.get_blogs()
    username = blogs.entry[0].author[0].name.text if blogs.entry else None
    hostnames = []
    for entry in blogs.entry:
      for link in entry.link:
        if link.type == 'text/html':
          domain = util.domain_from_link(link.href)
          if domain:
            hostnames.append(domain)
            break

    creds_json = oauth.credentials.to_json()
    BloggerV2Auth.get_or_insert(key_name=username,
                                hostnames=hostnames,
                                creds_json=creds_json)

    # redirect so that refreshing the page doesn't try to regenerate the oauth
    # token, which won't work.
    self.redirect('/?' + urllib.urlencode({
          'blogger_v2_username': username if username else 'No blogs found',
          'blogger_v2_hostnames': hostnames,
          'blogger_v2_credentials': creds_json,
          }, True))


application = webapp2.WSGIApplication([
    ('/blogger_v2/start', StartHandler),
    (oauth.callback_path, oauth.callback_handler()),
    ], debug=appengine_config.DEBUG)
