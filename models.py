"""Instagram OAuth drop-in.
"""

import logging
import urllib
import urllib2
import urlparse

from webutil import models

from google.appengine.ext import db


class BaseAuth(models.KeyNameModel):
  """Datastore base model class for an authenticated site.

  The key name is usually the user's username or id on the site.
  """

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
    return None

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
    # convert to list so we can modify later
    parsed = list(urlparse.urlparse(url))
    # query params are in index 4
    params = urlparse.parse_qsl(parsed[4]) + [('access_token', access_token)]
    parsed[4] = urllib.urlencode(params)
    url = urlparse.urlunparse(parsed)

    logging.debug('Fetching %s', url)
    return urllib2.urlopen(url, **kwargs)

  def http(self):
    """Returns an httplib2.Http that adds OAuth credentials to requests.

    Use this for making direct HTTP REST request to a site's API. Not guaranteed
    to be implemented by all sites.
    """
    raise NotImplementedError()

