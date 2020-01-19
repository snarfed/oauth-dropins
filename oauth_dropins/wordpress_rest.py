"""WordPress.com OAuth drop-in.

API docs:
https://developer.wordpress.com/docs/api/
https://developer.wordpress.com/docs/oauth2/

Note that unlike Blogger and Tumblr, WordPress.com's OAuth tokens are *per
blog*. It asks you which blog to use on its authorization page.

Also, wordpress.com doesn't let you use an oauth redirect URL with "local" or
"localhost" anywhere in it. : / A common workaround is to map an arbitrary host
to localhost in your /etc/hosts, e.g.:

127.0.0.1 my.dev.com

You can then test on your local machine by running dev_appserver and opening
http://my.dev.com:8080/ instead of http://localhost:8080/ .
"""
import logging
import urllib.parse, urllib.request

from google.cloud import ndb
from webob import exc

from . import handlers
from .models import BaseAuth
from .webutil import util
from .webutil.util import json_dumps, json_loads

WORDPRESS_CLIENT_ID = util.read('wordpress.com_client_id')
WORDPRESS_CLIENT_SECRET = util.read('wordpress.com_client_secret')
# URL templates. Can't (easily) use urllib.urlencode() because I want to keep
# the %(...)s placeholders as is and fill them in later in code.
GET_AUTH_CODE_URL = '&'.join((
    'https://public-api.wordpress.com/oauth2/authorize?',
    'scope=',  # wordpress doesn't seem to use scope
    'client_id=%(client_id)s',
    # redirect_uri here must be the same in the access token request!
    'redirect_uri=%(redirect_uri)s',
    'state=%(state)s',
    'response_type=code',
    ))
GET_ACCESS_TOKEN_URL = 'https://public-api.wordpress.com/oauth2/token'
API_USER_URL = 'https://public-api.wordpress.com/rest/v1/me?pretty=true'


class WordPressAuth(BaseAuth):
  """An authenticated WordPress user or page.

  Provides methods that return information about this user (or page) and make
  OAuth-signed requests to the WordPress REST API. Stores OAuth credentials in
  the datastore. See models.BaseAuth for usage details.

  WordPress-specific details: implements urlopen() but not api(). The key name
  is the blog hostname.
  """
  blog_id = ndb.StringProperty(required=True)
  blog_url = ndb.StringProperty(required=True)
  access_token_str = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty()

  def site_name(self):
    return 'WordPress'

  def user_display_name(self):
    """Returns the blog hostname.
    """
    if self.user_json:
      user = json_loads(self.user_json)
      return user.get('display_name') or user.get('username')
    else:
      return self.key_id()

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def urlopen(self, url, **kwargs):
    """Wraps urllib.request.urlopen() and adds OAuth credentials to the request.
    """
    kwargs.setdefault('headers', {})['authorization'] = \
        'Bearer ' + self.access_token_str
    try:
      return util.urlopen(urllib.request.Request(url, **kwargs))
    except BaseException as e:
      util.interpret_http_exception(e)
      raise


class StartHandler(handlers.StartHandler):
  """Starts WordPress auth. Requests an auth code and expects a redirect back.
  """
  NAME = 'wordpress.com'
  LABEL = 'WordPress.com'

  def redirect_url(self, state=None):
    assert WORDPRESS_CLIENT_ID and WORDPRESS_CLIENT_SECRET, \
      "Please fill in the wordpress.com_client_id and wordpress.com_client_secret files in your app's root directory."
    # TODO: CSRF protection
    return GET_AUTH_CODE_URL % {
      'client_id': WORDPRESS_CLIENT_ID,
      'redirect_uri': urllib.parse.quote_plus(self.to_url()),
      'state': urllib.parse.quote_plus(state if state else ''),
      }

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args, input_style='background-color: #3499CD', **kwargs)


class CallbackHandler(handlers.CallbackHandler):
  """The OAuth callback. Fetches an access token and stores it.
  """

  def get(self):
    # handle errors
    error = self.request.get('error')
    if error:
      error_description = urllib.parse.unquote_plus(
        self.request.get('error_description', ''))
      if error == 'access_denied':
        logging.info('User declined: %s', error_description)
        self.finish(None, state=self.request.get('state'))
        return
      else:
        raise exc.HTTPBadRequest('Error: %s %s ' % (error, error_description))

    # extract auth code and request access token
    auth_code = util.get_required_param(self, 'code')
    data = {
      'code': auth_code,
      'client_id': WORDPRESS_CLIENT_ID,
      'client_secret': WORDPRESS_CLIENT_SECRET,
      # redirect_uri here must be the same in the oauth code request!
      # (the value here doesn't actually matter since it's requested server side.)
      'redirect_uri': self.request.path_url,
      'grant_type': 'authorization_code',
    }
    resp = util.requests_post(GET_ACCESS_TOKEN_URL, data=data)
    logging.debug('Access token response: %s', resp.text)
    # TODO: handle errors, same JSON schema/fields as above

    try:
      resp = json_loads(resp.text)
      blog_id = resp['blog_id']
      blog_url = resp['blog_url']
      blog_domain = util.domain_from_link(resp['blog_url'])
      access_token = resp['access_token']
    except:
      logging.error('Could not decode JSON', stack_info=True)
      raise

    auth = WordPressAuth(id=blog_domain,
                         blog_id=blog_id,
                         blog_url=blog_url,
                         access_token_str=access_token)
    auth.user_json = auth.urlopen(API_USER_URL).read()
    auth.put()

    self.finish(auth, state=self.request.get('state'))
