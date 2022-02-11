"""Utility functions for calling signed Flickr API methods.

Supports Python 3. Should not depend on App Engine API or SDK packages.
"""
import logging
import re
import urllib.error, urllib.parse, urllib.request

import oauthlib.oauth1
import requests_oauthlib
import requests

from .webutil import util
from .webutil.util import json_dumps, json_loads

logger = logging.getLogger(__name__)

FLICKR_APP_KEY = util.read('flickr_app_key')
FLICKR_APP_SECRET = util.read('flickr_app_secret')


def signed_urlopen(url, token_key, token_secret, **kwargs):
  """Call :func:`urllib.request.urlopen`, signing the request with Flickr credentials.

  Args:
    url (string): the url to open
    token_key (string): user's access token
    token_secret (string): the user's access token secret
    timeout (Optional[int]): the request timeout, falls
      back to HTTP_TIMEOUT if not specified

  Returns:
    the file-like object that is the result of :func:`urllib.request.urlopen`
  """
  auth = oauthlib.oauth1.Client(
    FLICKR_APP_KEY,
    client_secret=FLICKR_APP_SECRET,
    resource_owner_key=token_key,
    resource_owner_secret=token_secret)
  uri, headers, body = auth.sign(url, **kwargs)
  try:
    return util.urlopen(urllib.request.Request(uri, body, headers))
  except BaseException as e:
    util.interpret_http_exception(e)
    raise


def raise_for_failure(url, code, msg):
  # https://www.flickr.com/services/api/flickr.auth.checkToken.html#Error%20Codes
  # invalid auth token or API key -> unauthorized
  http_code = 401 if code in (98, 100) else 400
  raise urllib.error.HTTPError(
    url, http_code, f'message={msg}, flickr code={int(code)}', {}, None)


def call_api_method(method, params, token_key, token_secret):
  """Call a Flickr API method.

  Flickr has one API endpoint, where different methods are called by name.

  If the "stat" field contains "fail", then this method creates
  an artificial HTTPError 400 or 401 depending on the type of failure.

  Args:
    method (string): the API method name (e.g. ``flickr.photos.getInfo``)
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
  url = 'https://api.flickr.com/services/rest?' + urllib.parse.urlencode(full_params)
  resp = signed_urlopen(url, token_key, token_secret)

  text = resp.read()
  try:
    body = json_loads(text)
  except BaseException:
    logger.warning(f'Ignoring malformed flickr response: {text[:1000]}')
    body = {}

  # Flickr returns HTTP success even for errors, so we have to fake it
  if body.get('stat') == 'fail':
    raise_for_failure(url, body.get('code'), body.get('message'))

  return body


def upload(params, file, token_key, token_secret):
  """Upload a photo or video to this user's Flickr account.

  Flickr uploads use their own API endpoint, that returns only XML.
  https://www.flickr.com/services/api/upload.api.html

  Unlike :func:`call_api_method`, this uses the requests library because
  :mod:`urllib` doesn't support multi-part POSTs on its own.

  Args:
    params (dict): the parameters to send to the API method
    file (file-like object): the image or video to upload
    token_key (string): the user's API access token
    token_secret (string): the user's API access token secret

  Return:
    dict containing the photo id (as 'id')

  Raises:
    :class:`requests.HTTPError` on HTTP error or :class:`urllib.error.HTTPError` if
    we get a stat='fail' response from Flickr.
  """
  upload_url = 'https://up.flickr.com/services/upload'
  auth = requests_oauthlib.OAuth1(
      client_key=FLICKR_APP_KEY,
      client_secret=FLICKR_APP_SECRET,
      resource_owner_key=token_key,
      resource_owner_secret=token_secret,
      signature_type=oauthlib.oauth1.SIGNATURE_TYPE_BODY)

  # create a request with files for signing
  faux_req = requests.Request(
    'POST', upload_url, data=params, auth=auth).prepare()
  # parse the signed parameters back out of the body
  data = urllib.parse.parse_qsl(faux_req.body.decode('utf-8'))

  # and use them in the real request
  resp = util.requests_post(upload_url, data=data, files={'photo': file})
  logger.debug(f'upload response: {resp}, {resp.text}')
  resp.raise_for_status()

  m = re.search(r'<rsp stat="(\w+)">', resp.text, re.DOTALL)
  if not m:
    raise BaseException(
      f'Expected response with <rsp stat="...">. Got: {resp.text}')

  stat = m.group(1)
  if stat == 'fail':
    m = re.search(r'<err code="(\d+)" msg="([^"]+)" />', resp.text, re.DOTALL)
    if not m:
      raise BaseException(
        f'Expected response with <err code="..." msg=".." />. Got: {resp.text}')
    raise_for_failure(upload_url, int(m.group(1)), m.group(2))

  m = re.search(r'<photoid>(\d+)</photoid>', resp.text, re.DOTALL)
  if not m:
    raise BaseException(
      f'Expected response with <photoid>...</photoid>. Got: {resp.text}')

  return {'id': m.group(1)}
