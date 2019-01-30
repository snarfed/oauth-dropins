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

WARNING: oauth2client is deprecated! google-auth is its successor.
https://google-auth.readthedocs.io/en/latest/oauth2client-deprecation.html
"""

import json
import logging
import re

import appengine_config
import google_signin
import handlers
import models
from webutil import util

try:
  from oauth2client.appengine import CredentialsModel, OAuth2Decorator, StorageByKeyName
except ImportError:
  from oauth2client.contrib.appengine import CredentialsModel, OAuth2Decorator, StorageByKeyName
from oauth2client.client import OAuth2Credentials
from gdata.blogger import client
from gdata import gauth
from google.appengine.ext import ndb
import httplib2


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


# Wrapper classes around the StorageByKeyName and CredentialsModel model classes
# to change their kinds so we can store separate creds for Google and Blogger.
# Without this, after you've signed into one, signing into the other tries to
# reuse the existing creds without re-requesting access for the new product and
# scope, which obviously fails. I hoped prompt=consent or
# include_granted_scopes=true or both would fix this, but no luck. :/
class StorageByKeyName_Blogger(StorageByKeyName):
  pass

class CredentialsModel_Blogger(CredentialsModel):
  pass


class StartHandler(handlers.StartHandler, handlers.CallbackHandler):
  """Connects a Blogger account. Authenticates via OAuth.
  """
  handle_exception = google_signin.handle_exception

  # extracts the Blogger id from a profile URL
  AUTHOR_URI_RE = re.compile(
    r'.*(?:blogger\.com/(?:feeds|profile)|(?:plus|profiles)\.google\.com)/([0-9]+)(?:/blogs)')
  # https://developers.google.com/blogger/docs/2.0/developers_guide_protocol#OAuth2Authorizing
  # (the scope for the v3 API is https://www.googleapis.com/auth/blogger)
  DEFAULT_SCOPE = 'https://www.blogger.com/feeds/'

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
        callback_path=to_path,
        prompt='consent',
        # https://developers.google.com/accounts/docs/OAuth2WebServer#incrementalAuth
        include_granted_scopes='true',
        _storage_class=StorageByKeyName_Blogger,
        _credentials_class=CredentialsModel_Blogger)

    class Handler(cls):
      @oauth_decorator.oauth_required
      def post(self):
        return self.get()

      @oauth_decorator.oauth_required
      def get(self):
        state = self.request.get('state')
        blogger = BloggerV2Auth.api_from_creds(oauth_decorator.credentials)
        try:
          blogs = blogger.get_blogs()
        except BaseException, e:
          # this api call often returns 401 Unauthorized for users who aren't
          # signed up for blogger and/or don't have any blogs.
          util.interpret_http_exception(e)
          # we can't currently intercept declines for Google or Blogger, so the
          # only time we return a None auth entity right now is on error.
          self.finish(None, state=state)
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

        creds_json = oauth_decorator.credentials.to_json()

        # extract profile picture URL
        picture_url = None
        for author in blogs.author:
          for child in author.children:
            if child.tag.split(':')[-1] == 'image':
              picture_url = child.get_attributes('src')[0].value
              break

        auth = BloggerV2Auth(id=id,
                             name=author.name.text,
                             picture_url=picture_url,
                             creds_json=creds_json,
                             user_atom=str(author),
                             blogs_atom=str(blogs),
                             blog_ids=blog_ids,
                             blog_titles=blog_titles,
                             blog_hostnames=blog_hostnames)
        auth.put()
        self.finish(auth, state=state)


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
