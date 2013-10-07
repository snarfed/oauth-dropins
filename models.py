"""Instagram OAuth drop-in.
"""

import logging
import urllib2

from webutil import models

from google.appengine.ext import db


class BaseAuth(models.KeyNameModel):
  """Datastore base model class for an authenticated site.

  The key name is usually the user's username or id on the site.
  """
  auth_code = db.StringProperty(required=True)
  access_token = db.StringProperty(required=True)
  info_json = db.TextProperty(required=True)

  def api(self):
    """Returns the site-specific API object instance, if any.

    Only some sites implement this: currently Dropbox, Instagram, Google+, and
    Tumblr.
    """
    return None

  def api_urlopen(self):
    """Wraps urllib2.urlopen() and inserts an OAuth access token or signature.
    """
    raise NotImplementedError()
