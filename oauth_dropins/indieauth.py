"""IndieAuth drop-in.

https://indieauth.com/developers
"""

import json
import logging

import appengine_config
import handlers
import models
from webutil import util

from google.appengine.ext import ndb


AUTHENTICATE_URL = 'https://indieauth.com/auth'


class IndieAuth(models.BaseAuth):
  """An authenticated IndieAuth user.

  Provides methods that return information about this user. Stores credentials
  in the datastore. Key is the domain name. See models.BaseAuth for usage
  details.
  """
  # access token
  token = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)  # generally this has only 'me'

  def site_name(self):
    return 'IndieAuth'

  def user_display_name(self):
    """Returns the user's domain."""
    return self.key.string_id()

  def access_token(self):
    """Returns theAuth access token string."""
    return self.token


class StartHandler(handlers.StartHandler):
  """Starts the IndieAuth flow."""
  def redirect_url(self, state=None):

    logging.info('Redirecting to IndieAuth: %s', url)
    return url


class CallbackHandler(handlers.CallbackHandler):
  """The callback. ..."""
  def get(self):
    # ...
    self.finish(indie_auth, state=self.request.get('state'))
