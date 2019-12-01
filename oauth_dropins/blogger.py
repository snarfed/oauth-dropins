"""Blogger v2 GData API OAuth drop-in.

Blogger API docs:
https://developers.google.com/blogger/docs/2.0/developers_guide_protocol

Python GData API docs:
http://gdata-python-client.googlecode.com/hg/pydocs/gdata.blogger.data.html

Uses google-api-python-client to auth via OAuth 2. This describes how to get
gdata-python-client to use an OAuth 2 token from google-api-python-client:
http://blog.bossylobster.com/2012/12/bridging-oauth-20-objects-between-gdata.html#comment-form

Support was added to gdata-python-client here:
https://code.google.com/p/gdata-python-client/source/detail?r=ecb1d49b5fbe05c9bc6c8525e18812ccc02badc0
"""
from __future__ import absolute_import, unicode_literals
from future import standard_library
standard_library.install_aliases()

import logging
import re

import appengine_config
from appengine_config import ndb_client

from gdata.blogger.client import BloggerClient
from google.cloud import ndb
from requests_oauthlib import OAuth2Session

from . import google_signin, handlers, models
from .webutil import handlers as webutil_handlers
from .webutil import util
from .webutil.util import json_dumps, json_loads

AUTH_CODE_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
ACCESS_TOKEN_URL = 'https://www.googleapis.com/oauth2/v4/token'


class BloggerUser(models.BaseAuth):
  """An authenticated Blogger user.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to the Blogger API. Stores OAuth credentials in the
  datastore. See models.BaseAuth for usage details.

  Blogger-specific details: implements api() but not urlopen(). api() returns a
  gdata.blogger.client.BloggerClient. The datastore entity key name is the
  Blogger user id.
  """
  name = ndb.StringProperty(required=True)
  creds_json = ndb.TextProperty(required=True)
  user_atom = ndb.TextProperty(required=True)
  blogs_atom = ndb.TextProperty(required=True)
  picture_url = ndb.TextProperty(required=True)

  # the elements in both of these lists match
  blog_ids = ndb.StringProperty(repeated=True)
  blog_titles = ndb.StringProperty(repeated=True)
  blog_hostnames = ndb.StringProperty(repeated=True)

  def site_name(self):
    return 'Blogger'

  def user_display_name(self):
    """Returns the user's Blogger username.
    """
    return self.name

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return json_loads(self.creds_json)['access_token']

  def _api(self):
    """Returns a gdata.blogger.client.BloggerClient.
    """
    return BloggerClient(auth_token=self)

  def modify_token(self, http_request):
    http_request.headers['Authorization'] = 'Bearer %s' % self.access_token()


class Scopes(object):
  # https://developers.google.com/blogger/docs/2.0/developers_guide_protocol#OAuth2Authorizing
  # (the scope for the v3 API is https://www.googleapis.com/auth/blogger)
  DEFAULT_SCOPE = 'https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/blogger openid'
  SCOPE_SEPARATOR = ' '


class StartHandler(Scopes, handlers.StartHandler):
  """Connects a Blogger account. Authenticates via OAuth."""
  NAME = 'blogger'
  LABEL = 'Blogger'

  handle_exception = webutil_handlers.handle_exception

  def redirect_url(self, state=None):
    assert (appengine_config.GOOGLE_CLIENT_ID and
            appengine_config.GOOGLE_CLIENT_SECRET), \
            "Please fill in the google_client_id and google_client_secret files in your app's root directory."

    session = OAuth2Session(appengine_config.GOOGLE_CLIENT_ID, scope=self.scope,
                            redirect_uri=self.to_url())
    auth_url, state = session.authorization_url(
      AUTH_CODE_URL,
      # ask for a refresh token so we can get an access token offline
      access_type='offline', prompt='consent',
      # https://developers.google.com/accounts/docs/OAuth2WebServer#incrementalAuth
      include_granted_scopes='true')
    return auth_url


class CallbackHandler(Scopes, handlers.CallbackHandler):
  """Finishes the OAuth flow."""

  # extracts the Blogger id from a profile URL
  AUTHOR_URI_RE = re.compile(
    r'.*(?:blogger\.com/(?:feeds|profile)|(?:plus|profiles)\.google\.com)/([0-9]+)(?:/blogs)')

  def get(self):
    with ndb_client.context():
      # handle errors
      state = self.request.get('state')
      error = self.request.get('error')
      desc = self.request.get('error_description')
      if error:
        msg = 'Error: %s: %s' % (error, desc)
        logging.info(msg)
        if error == 'access_denied':
          return self.finish(None, state=state)
        else:
          raise exc.HTTPBadRequest(msg)

      # extract auth code and request access token
      session = OAuth2Session(appengine_config.GOOGLE_CLIENT_ID, scope=self.scope,
                              redirect_uri=self.request.path_url)
      session.fetch_token(ACCESS_TOKEN_URL,
                          client_secret=appengine_config.GOOGLE_CLIENT_SECRET,
                          authorization_response=self.request.url)

      blogger = BloggerClient()
      try:
        blogs = blogger.get_blogs(access_token=session.access_token)
      except BaseException as e:
        # this api call often returns 401 Unauthorized for users who aren't
        # signed up for blogger and/or don't have any blogs.
        util.interpret_http_exception(e)
        return

      for id in ([a.uri.text for a in blogs.author if a.uri] +
                 [l.href for l in blogs.link if l]):
        if not id:
          continue
        match = self.AUTHOR_URI_RE.match(id)
        if match:
          id = match.group(1)
        else:
          logging.warning("Couldn't parse %s , using entire value as id", id)
        break

      blog_ids = []
      blog_titles = []
      blog_hostnames = []
      for blog in blogs.entry:
        blog_ids.append(blog.get_blog_id() or blog.get_blog_name())
        blog_titles.append(blog.title.text)
        blog_hostnames.append(util.domain_from_link(blog.GetHtmlLink().href)
                              if blog.GetHtmlLink() else None)

      # extract profile picture URL
      picture_url = None
      for author in blogs.author:
        for child in author.children:
          if child.tag.split(':')[-1] == 'image':
            picture_url = child.get_attributes('src')[0].value
            break

      user = BloggerUser(id=id,
                         name=author.name.text,
                         picture_url=picture_url,
                         creds_json=json_dumps(session.token),
                         user_atom=str(author),
                         blogs_atom=str(blogs),
                         blog_ids=blog_ids,
                         blog_titles=blog_titles,
                         blog_hostnames=blog_hostnames)
      user.put()
      self.finish(user, state=state)
