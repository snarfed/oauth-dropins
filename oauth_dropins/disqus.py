"""Disqus OAuth drop-in.

Disqus API docs: https://disqus.com/api/docs/

This drop-in is even more similar to Instagram than Instagram is to
Facebook. Differences:

- urlopen must pass the api_key with each request (in addition to the
  access_token)
- Response to access_token does not give much information about the user,
  so we additionally fetch /user/details before saving
- Deny appears to be broken on Disqus's side (clicking "No Thanks" has
  no effect), so we ignore that possibility for now.

TODO unify Disqus, Facebook, and Instagram
"""
import json
import logging
import urllib
from webob import exc

from webutil import util

import appengine_config
import handlers
import models

from google.appengine.ext import ndb


GET_AUTH_CODE_URL = (
    'https://disqus.com/api/oauth/2.0/authorize/?' +
    '&'.join((
        'client_id=%(client_id)s',
        'scope=%(scope)s',
        'response_type=code',
        'redirect_uri=%(redirect_uri)s',
    )))

GET_ACCESS_TOKEN_URL = 'https://disqus.com/api/oauth/2.0/access_token/'

USER_DETAILS_URL = 'https://disqus.com/api/3.0/users/details.json?user=%d'


class DisqusAuth(models.BaseAuth):
  """An authenticated Disqus user.

  Provides methods that return information about this user (or page)
  and make OAuth-signed requests to Instagram's HTTP-based
  APIs. Stores OAuth credentials in the datastore. See models.BaseAuth
  for usage details.

  Disqus-specific details: implements urlopen() but not http() or api().
  The key name is the Disqus user id.
  """
  auth_code = ndb.StringProperty(required=True)
  access_token_str = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty(required=True)

  def site_name(self):
    return 'Disqus'

  def user_display_name(self):
    """Returns the user's name.
    """
    return json.loads(self.user_json)['name']

  def access_token(self):
    """Returns the OAuth access token string.
    """
    return self.access_token_str

  def urlopen(self, url, **kwargs):
    """Wraps urllib2.urlopen() and adds OAuth credentials to the request.
    """
    # TODO does work for POST requests? key is always passed as a
    # query param, regardless of method.
    return models.BaseAuth.urlopen_access_token(
        url, self.access_token_str,
        appengine_config.DISQUS_CLIENT_ID,
        **kwargs)


class StartHandler(handlers.StartHandler):
  """Starts Disqus auth. Requests an auth code and expects a redirect back.
  """

  # Disqus scopes are comma separated: read, write, admin, email
  # https://disqus.com/api/docs/requests/#data-availability
  DEFAULT_SCOPE = 'read'

  def redirect_url(self, state=None):
      assert (appengine_config.DISQUS_CLIENT_ID and
              appengine_config.DISQUS_CLIENT_SECRET), (
          "Please fill in the %s and %s files in your app's root directory." % (
              ('disqus_client_id_local', 'disqus_client_secret_local')
              if appengine_config.DEBUG else
              ('disqus_client_id', 'disqus_client_secret')
          ))
      return GET_AUTH_CODE_URL % {
        'client_id': appengine_config.DISQUS_CLIENT_ID,
        'scope': self.scope,
        'redirect_uri': urllib.quote_plus(self.to_url(state=state)),
      }


class CallbackHandler(handlers.CallbackHandler):
  """The auth callback. Fetches an access token, stores it, and redirects home.
  """
  def get(self):
    if self.handle_error():
      return

    # https://disqus.com/api/docs/auth/
    auth_code = util.get_required_param(self, 'code')
    data = {
        'grant_type': 'authorization_code',
        'client_id': appengine_config.DISQUS_CLIENT_ID,
        'client_secret': appengine_config.DISQUS_CLIENT_SECRET,
        'redirect_uri': self.request_url_with_state(),
        'code': auth_code,
    }

    resp = util.urlopen(GET_ACCESS_TOKEN_URL, data=urllib.urlencode(data)).read()
    try:
      data = json.loads(resp)
    except (ValueError, TypeError):
      logging.exception('Bad response:\n%s', resp)
      raise exc.HttpBadRequest('Bad Disqus response to access token request')

    access_token = data['access_token']
    user_id = data['user_id']
    # TODO is a username key preferred?
    # username = data['username']

    auth = DisqusAuth(id=str(user_id),
                      auth_code=auth_code,
                      access_token_str=access_token)

    resp = auth.urlopen(USER_DETAILS_URL % user_id).read()
    try:
      user_data = json.loads(resp)['response']
    except (ValueError, TypeError):
      logging.exception('Bad response:\n%s', resp)
      raise exc.HttpBadRequest('Bad Disqus response to user details request')

    auth.user_json = json.dumps(user_data)
    logging.info('created disqus auth %s', auth)
    auth.put()
    self.finish(auth, state=self.request.get('state'))

  def handle_error(handler):
    """Handles any error reported in the callback query parameters.

    Args:
      handler: CallbackHandler

    Returns:
      True if there was an error, False otherwise.
    """
    error = handler.request.get('error')
    if error:
      if error == 'access_denied':
        logging.info('User declined')
        handler.finish(None, state=handler.request.get('state'))
        return True
      else:
        raise exc.HTTPBadRequest(error)

    return False
