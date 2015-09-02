"""Utility functions for calling signed Flickr API methods.
"""

import appengine_config
import oauthlib.oauth1
import urllib
import urllib2
import json
import logging
from webutil import util


def signed_urlopen(url, token_key, token_secret, **kwargs):
  """Call urllib2.urlopen, signing the request with Flickr credentials.
  Args:
    url (string): the url to open
    token_key (string): user's access token
    token_secret (string): the user's access token secret
    timeout (Optional[int]): the request timeout, falls
      back to HTTP_TIMEOUT if not specified

  Returns:
    the file-like object that is the result of urllib2.urlopen
  """
  auth = oauthlib.oauth1.Client(
    appengine_config.FLICKR_APP_KEY,
    client_secret=appengine_config.FLICKR_APP_SECRET,
    resource_owner_key=token_key,
    resource_owner_secret=token_secret)
  uri, headers, body = auth.sign(url, **kwargs)
  timeout = kwargs.pop('timeout', appengine_config.HTTP_TIMEOUT)
  logging.debug('Fetching %s', uri)
  try:
    return urllib2.urlopen(urllib2.Request(uri, body, headers),
                           timeout=timeout)
  except BaseException, e:
    util.interpret_http_exception(e)
    raise


def call_api_method(method, params, token_key, token_secret):
  """Call a Flickr API method. Flickr has one API endpoint, where
  different methods are called by name.

  Args:
    method (string): the API method name (e.g. flickr.photos.getInfo)
    params (dict): the parameters to send to the API method
    token_key (string): the user's API access token
    token_secret (string): the user's API access token secret

  Return:
    json object response from the API
  """
  full_params = {
    'nojsoncallback': 1,
    'format': 'json',
    'method': method,
  }
  full_params.update(params)
  resp = signed_urlopen('https://api.flickr.com/services/rest?'
                        + urllib.urlencode(full_params),
                        token_key, token_secret)
  return json.load(resp)
