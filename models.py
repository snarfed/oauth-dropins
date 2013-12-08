"""Base datastore model class for an authenticated account.
"""

import logging
import urllib
import urllib2
import urlparse

from webutil import models
from webutil import util

from google.appengine.ext import db


class BaseAuth(models.KeyNameModel):
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

    Returns None if the site doesn 't have a Python API. Only some do, currently
    Blogger, Instagram, Google+, and Tumblr.
    """
    if self._api is None:
      self._api_obj = self._api()
    return self._api_obj

  def access_token(self):
    """Returns the OAuth access token.

    This is a string for OAuth 2 sites or a (string key, string secret) tuple
    for OAuth 1.1 sites (currently just Twitter and Tumblr).
    """
    raise NotImplementedError()

  def urlopen(self, url, data=None, timeout=None):
    """Wraps urllib2.urlopen() and adds OAuth credentials to the request.

    Use this for making direct HTTP REST request to a site's API. Not guaranteed
    to be implemented by all sites.

    The arguments, return value (urllib2.Response), and exceptions raised
    (urllib2.URLError) are the same as urllib2.urlopen.
    """
    raise NotImplementedError()

  @staticmethod
  def urlopen_access_token(url, access_token, **kwargs):
    """Wraps urllib2.urlopen() and adds an access_token query parameter.
    """
    log_url = util.add_query_params(url, [('access_token', access_token[:4] + '...')])
    logging.info('Fetching %s', log_url)
    url = util.add_query_params(url, [('access_token', access_token)])
    return urllib2.urlopen(url, **kwargs)

  def http(self):
    """Returns an httplib2.Http that adds OAuth credentials to requests.

    Use this for making direct HTTP REST request to a site's API. Not guaranteed
    to be implemented by all sites.
    """
    raise NotImplementedError()


class OAuthRequestToken(models.KeyNameModel):
  """Datastore model class for an OAuth 1.1 request token.

  This is only intermediate data. Client should use BaseAuth subclasses to make
  API calls.

  The key name is the token key.
  """
  token_secret = db.StringProperty(required=True)
  state = db.StringProperty(required=False)
