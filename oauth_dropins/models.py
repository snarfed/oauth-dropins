"""Base datastore model class for an authenticated account.
"""

import logging
import urllib2

import appengine_config
import handlers
from webutil import models
from webutil import util

from google.appengine.ext import ndb


class BaseAuth(models.StringIdModel):
  """Datastore base model class for an authenticated user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the site's API(s). Stores OAuth credentials in the datastore.
  The key name is usually the user's username or id.

  Many sites provide additional methods and store additional user information in
  a JSON property.
  """
  # A site-specific API object. Initialized on demand.
  _api_obj = None

  def site_name(self):
    """Returns the string name of the site, e.g. 'Facebook'.
    """
    raise NotImplementedError()

  def user_display_name(self):
    """Returns a string user identifier, e.g. 'Ryan Barrett' or 'snarfed'.
    """
    raise NotImplementedError()

  def api(self):
    """Returns the site-specific Python API object, if any.

    Returns None if the site doesn't have a Python API. Only some do, currently
    Blogger, Instagram, Google+, and Tumblr.
    """
    if self._api_obj is None:
      self._api_obj = self._api()
    return self._api_obj

  def access_token(self):
    """Returns the OAuth access token.

    This is a string for OAuth 2 sites or a (string key, string secret) tuple
    for OAuth 1.1 sites (currently just Twitter and Tumblr).
    """
    raise NotImplementedError()

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds OAuth credentials to the request.

    Use this for making direct HTTP REST request to a site's API. Not guaranteed
    to be implemented by all sites.

    The arguments, return value (urllib2.Response), and exceptions raised
    (urllib2.URLError) are the same as urllib2.urlopen.
    """
    raise NotImplementedError()

  def is_authority_for(self, key):
    """When disabling or modifying an account, it's useful to re-auth the
    user to make sure they have have permission to modify that
    account. Typically this means the auth entity represents the exact
    same user, but in some cases (e.g., Facebook Pages), a user may
    control several unique identities. So authenticating as a user
    should give you authority over their pages.

    Args:
      key: ndb.Key

    Returns:
      boolean, true if key represents the same account as this entity
    """
    return self.key == key

  @staticmethod
  def urlopen_access_token(url, access_token, api_key=None, **kwargs):
    """Wraps urllib2.urlopen() and adds an access_token query parameter.

    Kwargs are passed through to urlopen().
    """
    log_params = [('access_token', access_token[:4] + '...')]
    real_params = [('access_token', access_token)]
    if api_key:
      log_params.append(('api_key', api_key[:4] + '...'))
      real_params.append(('api_key', api_key))
    log_url = util.add_query_params(url, log_params)
    url = util.add_query_params(url, real_params)

    try:
      return util.urlopen(url, **kwargs)
    except BaseException, e:
      util.interpret_http_exception(e)
      raise

  def http(self):
    """Returns an httplib2.Http that adds OAuth credentials to requests.

    Use this for making direct HTTP REST request to a site's API. Not guaranteed
    to be implemented by all sites.
    """
    raise NotImplementedError()


class OAuthRequestToken(models.StringIdModel):
  """Datastore model class for an OAuth 1.1 request token.

  This is only intermediate data. Client should use BaseAuth subclasses to make
  API calls.

  The key name is the token key.
  """
  token_secret = ndb.StringProperty(required=True)
  state = ndb.StringProperty(required=False)
