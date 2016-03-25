"""IndieAuth drop-in.

https://indieauth.com/developers
"""

import json
import logging
import urllib
import urlparse
from webob import exc

import bs4
import appengine_config
import handlers
import models
from webutil import util

from google.appengine.ext import ndb


INDIEAUTH_URL = 'https://indieauth.com/auth'


def discover_authorization_endpoint(me):
  """Fetch a URL and look for authorization_endpoint Link header or
  rel-value.

  Args:
    me: string, URL to fetch

  Return:
    string, the discovered indieauth URL or the default indieauth.com URL
  """
  resp = util.requests_get(me)
  if resp.status_code // 100 != 2:
    logging.warning(
      'could not fetch user url "%s". got response code: %d',
      me, resp.status_code)
    return INDIEAUTH_URL
  # check authorization_endpoint header first
  auth_endpoint = resp.links.get('authorization_endpoint', {}).get('url')
  if auth_endpoint:
    return auth_endpoint
  # check the html content
  soup = bs4.BeautifulSoup(resp.text)
  auth_link = soup.find('link', {'rel': 'authorization_endpoint'})
  auth_endpoint = auth_link and auth_link.get('href')
  if auth_endpoint:
    return auth_endpoint
  return INDIEAUTH_URL


class IndieAuth(models.BaseAuth):
  """An authenticated IndieAuth user.

  Provides methods that return information about this user. Stores credentials
  in the datastore. Key is the domain name. See models.BaseAuth for usage
  details.
  """
  # access token
  user_json = ndb.TextProperty(required=True)  # generally this has only 'me'

  def site_name(self):
    return 'IndieAuth'

  def user_display_name(self):
    """Returns the user's domain."""
    return self.key.string_id()


class StartHandler(handlers.StartHandler):
  """Starts the IndieAuth flow. Requires the 'me' parameter with the
  user URL that we want to authenticate.
  """
  def redirect_url(self, state=None):
    assert appengine_config.INDIEAUTH_CLIENT_ID, (
      "Please fill in the indieauth_client_id in your app's root directory.")

    me = util.get_required_param(self, 'me')
    redirect_uri = self.to_url()
    endpoint = discover_authorization_endpoint(me)

    url = endpoint + '?' + urllib.urlencode({
      'me': me,
      'client_id': appengine_config.INDIEAUTH_CLIENT_ID,
      'redirect_uri': redirect_uri,
      'state': state,
    })

    logging.info('Redirecting to IndieAuth: %s', url)
    return str(url)


class CallbackHandler(handlers.CallbackHandler):
  """The callback handler from the IndieAuth request. POSTs back to the
  auth endpoint to verify the authentication code."""
  def get(self):
    me = util.get_required_param(self, 'me')
    code = util.get_required_param(self, 'code')
    state = util.get_required_param(self, 'state')
    endpoint = discover_authorization_endpoint(me)

    resp = util.requests_post(endpoint, data={
      'me': me,
      'client_id': appengine_config.INDIEAUTH_CLIENT_ID,
      'code': code,
      'redirect_uri': self.request.path_url,
      'state': state,
    })

    if resp.status_code // 100 == 2:
      data = urlparse.parse_qs(resp.content)
      if data.get('me'):
        verified = data.get('me')[0]
        indie_auth = IndieAuth(id=verified, user_json=json.dumps({
          'me': verified,
        }))
        indie_auth.put()
        self.finish(indie_auth, state=state)
      else:
        raise exc.HTTPBadRequest(
          'Verification response missing required "me" field')
    else:
      raise exc.HTTPBadRequest('IndieAuth verification failed: %s' % resp.text)
