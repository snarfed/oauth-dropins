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
import mf2py
import mf2util
import models
import requests
from webutil import util

from google.appengine.ext import ndb


INDIEAUTH_URL = 'https://indieauth.com/auth'


def discover_authorization_endpoint(me, resp=None):
  """Fetch a URL and look for authorization_endpoint Link header or
  rel-value.

  Args:
    me: string, URL to fetch
    resp: requests.Response (optional), re-use response if it's already been fetched

  Return:
    string, the discovered indieauth URL or the default indieauth.com URL
  """
  try:
    resp = resp or util.requests_get(me)
  except requests.RequestException as e:
    raise exc.HTTPBadRequest(str(e))

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


def build_user_json(me, resp=None):
  """user_json contains an h-card, rel-me links, and "me"

  Args:
    me: string, URL of the user, returned by
    resp: requests.Response (optional), re-use response if it's already been fetched

  Return:
    dict, with 'me', the URL for this person; 'h-card', the representative h-card
      for this page; 'rel-me', a list of rel-me URLs found at this page
  """
  user_json = {'me': me}

  resp = resp or util.requests_get(me)
  if resp.status_code // 100 != 2:
    logging.warning(
      'could not fetch user url "%s". got response code: %d',
      me, resp.status_code)
    return user_json
  # Requests doesn't look at the HTML body to find <meta charset>
  # tags, so if the character encoding isn't given in a header, then
  # we pass on the raw bytes and let BS4 deal with it.
  p = mf2py.parse(doc=resp.text
                  if 'charset' in resp.headers.get('content-type', '')
                  else resp.content, url=me)
  user_json['rel-me'] = p.get('rels', {}).get('me')
  user_json['h-card'] = mf2util.representative_hcard(p, me)
  logging.debug('built user-json %r', user_json)
  return util.trim_nulls(user_json)


class IndieAuth(models.BaseAuth):
  """An authenticated IndieAuth user.

  Provides methods that return information about this user. Stores credentials
  in the datastore. Key is the domain name. See models.BaseAuth for usage
  details.
  """
  user_json = ndb.TextProperty(required=True)  # generally this has only 'me'

  def site_name(self):
    return 'IndieAuth'

  def user_display_name(self):
    """Returns the user's domain."""
    return self.key.string_id()

  def access_token(self):
    """Return the access token, N/A for IndieAuth"""
    return None


class StartHandler(handlers.StartHandler):
  """Starts the IndieAuth flow. Requires the 'me' parameter with the
  user URL that we want to authenticate.
  """
  def redirect_url(self, state=None, me=None):
    assert appengine_config.INDIEAUTH_CLIENT_ID, (
      "Please fill in the indieauth_client_id in your app's root directory.")

    if not me:
      me = util.get_required_param(self, 'me')
    parsed = urlparse.urlparse(me)
    if not parsed.scheme:
      me = 'http://' + me

    redirect_uri = self.to_url()
    endpoint = discover_authorization_endpoint(me)

    url = endpoint + '?' + urllib.urlencode({
      'me': me,
      'client_id': appengine_config.INDIEAUTH_CLIENT_ID,
      'redirect_uri': redirect_uri,
      'state': util.encode_oauth_state({
        'endpoint': endpoint,
        'me': me,
        'state': state,
      }),
    })

    logging.info('Redirecting to IndieAuth: %s', url)
    return str(url)


class CallbackHandler(handlers.CallbackHandler):
  """The callback handler from the IndieAuth request. POSTs back to the
  auth endpoint to verify the authentication code."""
  def get(self):
    code = util.get_required_param(self, 'code')
    state = util.decode_oauth_state(util.get_required_param(self, 'state'))

    endpoint = state.get('endpoint')
    me = state.get('me')
    if not endpoint or not me:
        raise exc.HTTPBadRequest("invalid state parameter")

    state = state.get('state') or ''
    validate_resp = util.requests_post(endpoint, data={
      'me': me,
      'client_id': appengine_config.INDIEAUTH_CLIENT_ID,
      'code': code,
      'redirect_uri': self.request.path_url,
      'state': state,
    })

    if validate_resp.status_code // 100 == 2:
      data = util.sniff_json_or_form_encoded(validate_resp.content)
      if data.get('me'):
        verified = data.get('me')
        user_json = build_user_json(verified)
        indie_auth = IndieAuth(id=verified, user_json=json.dumps(user_json))
        indie_auth.put()
        self.finish(indie_auth, state=state)
      else:
        raise exc.HTTPBadRequest(
          'Verification response missing required "me" field')
    else:
      raise exc.HTTPBadRequest('IndieAuth verification failed: %s %s' %
                               (validate_resp.status_code, validate_resp.text))
