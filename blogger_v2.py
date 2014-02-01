"""Blogger v2 GData API OAuth drop-in.

Blogger API docs:
https://developers.google.com/blogger/docs/2.0/developers_guide_protocol

Uses google-api-python-client to auth via OAuth 2. This describes how to get
gdata-python-client to use an OAuth 2 token from google-api-python-client:
http://blog.bossylobster.com/2012/12/bridging-oauth-20-objects-between-gdata.html#comment-form

Support was added to gdata-python-client here:
https://code.google.com/p/gdata-python-client/source/detail?r=ecb1d49b5fbe05c9bc6c8525e18812ccc02badc0
"""

import json
import logging
import re
import urllib
import urlparse

import appengine_config
import googleplus
import handlers
import models
from webutil import util

from oauth2client.appengine import OAuth2Decorator
from oauth2client.client import Credentials, OAuth2Credentials
from gdata.blogger import client
from gdata import gauth
from google.appengine.api import users
from google.appengine.ext import ndb
import httplib2
import webapp2


# global. initialized in StartHandler.to_path().
oauth_decorator = None


class BloggerV2Auth(models.BaseAuth):
  """An authenticated Blogger user.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to the Blogger API. Stores OAuth credentials in the
  datastore. See models.BaseAuth for usage details.

  Blogger-specific details: implements http() and api() but not urlopen(). api()
  returns a gdata.blogger.client.BloggerClient. The datastore entity key name is
  the Blogger user id.
  """
  name = ndb.StringProperty(required=True)
  hostnames = ndb.StringProperty(repeated=True)
  creds_json = ndb.TextProperty(required=True)
  user_atom = ndb.TextProperty(required=True)
  blogs_atom = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Blogger'

  def user_display_name(self):
    """Returns the user's Blogger username.
    """
    return self.name

  def creds(self):
    """Returns an oauth2client.OAuth2Credentials.
    """
    return OAuth2Credentials.from_json(self.creds_json)

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return json.loads(self.creds_json)['access_token']

  def http(self):
    """Returns an httplib2.Http that adds OAuth credentials to requests.
    """
    http = httplib2.Http()
    self.creds().authorize(http)
    return http

  @staticmethod
  def api_from_creds(oauth2_creds):
    """Returns a gdata.blogger.client.BloggerClient.

    Args:
      oauth2_creds: OAuth2Credentials
    """
    # this must be a client ie subclass of GDClient, since that's what
    # OAuth2TokenFromCredentials.authorize() expects, *not* a service ie
    # subclass of GDataService.
    blogger = client.BloggerClient()
    gauth.OAuth2TokenFromCredentials(oauth2_creds).authorize(blogger)
    return blogger

  def _api(self):
    """Returns a gdata.blogger.client.BloggerClient.
    """
    return BloggerV2Auth.api_from_creds(self.creds())


class StartHandler(handlers.StartHandler, handlers.CallbackHandler):
  """Connects a Blogger account. Authenticates via OAuth.
  """
  handle_exception = googleplus.handle_exception

  # extracts the Blogger id from a profile URL
  AUTHOR_URI_RE = re.compile('.*blogger\.com/profile/([0-9]+)')

  # https://developers.google.com/blogger/docs/2.0/developers_guide_protocol#OAuth2Authorizing
  # (the scope for the v3 API is https://www.googleapis.com/auth/blogger)
  DEFAULT_SCOPE = 'http://www.blogger.com/feeds/'

  @classmethod
  def to(cls, to_path, scopes=None):
    """Override this since we need to_path to instantiate the oauth decorator.
    """
    global oauth_decorator
    if oauth_decorator is None:
      oauth_decorator = OAuth2Decorator(
        client_id=appengine_config.GOOGLE_CLIENT_ID,
        client_secret=appengine_config.GOOGLE_CLIENT_SECRET,
        scope=cls.make_scope_str(scopes),
        callback_path=to_path)

    class Handler(cls):
      @oauth_decorator.oauth_required
      def post(self):
        return self.get()

      @oauth_decorator.oauth_required
      def get(self):
        blogger = BloggerV2Auth.api_from_creds(oauth_decorator.credentials)
        blogs = blogger.get_blogs()
        author = blogs.author[0]
        match = self.AUTHOR_URI_RE.match(author.uri.text)
        if not match:
          raise exc.HTTPBadRequest('Could not parse author URI: %s', author.uri)
        id = match.group(1)
        hostnames = [util.domain_from_link(blog.GetHtmlLink().href)
                     for blog in blogs.entry if blog.GetHtmlLink()]

        creds_json = oauth_decorator.credentials.to_json()
        auth = BloggerV2Auth(id=id,
                             name=author.name.text,
                             hostnames=hostnames,
                             creds_json=creds_json,
                             user_atom=str(author),
                             blogs_atom=str(blogs))
        auth.put()
        self.finish(auth, state=self.request.get('state'))


    return Handler


class CallbackHandler(object):
  """OAuth callback handler factory.
  """
  @staticmethod
  def to(to_path):
    StartHandler.to_path = to_path
    global oauth_decorator
    assert oauth_decorator
    return oauth_decorator.callback_handler()
