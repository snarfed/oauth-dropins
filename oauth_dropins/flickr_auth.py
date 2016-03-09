"""Utility functions for calling signed Flickr API methods.
"""

import appengine_config
from webutil import util

import oauthlib.oauth1
import requests_oauthlib
import requests

import json
import logging
import re
import urllib
import urllib2
import urlparse


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
  try:
    return util.urlopen(urllib2.Request(uri, body, headers))
  except BaseException, e:
    util.interpret_http_exception(e)
    raise


def raise_for_failure(url, code, msg):
  # https://www.flickr.com/services/api/flickr.auth.checkToken.html#Error%20Codes
  # invalid auth token or API key -> unauthorized
  http_code = 401 if code == 98 or code == 100 else 400
  raise urllib2.HTTPError(
    url, http_code, 'message=%s, flickr code=%d' % (msg, code), {}, None)


def call_api_method(method, params, token_key, token_secret):
  """Call a Flickr API method. Flickr has one API endpoint, where
  different methods are called by name.

  If the "stat" field contains "fail", then this method creates
  an artificial HTTPError 400 or 401 depending on the type of failure.

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
  url = 'https://api.flickr.com/services/rest?' + urllib.urlencode(full_params)
  resp = signed_urlopen(url, token_key, token_secret)

  text = resp.read()
  try:
    body = json.loads(text)
  except BaseException:
    logging.warning('Ignoring malformed flickr response: %s', text[:1000])
    body = {}

  # Flickr returns HTTP success even for errors, so we have to fake it
  if body.get('stat') == 'fail':
    raise_for_failure(url, body.get('code'), body.get('message'))

  return body


def upload(params, file, token_key, token_secret):
  """Upload a photo or video to this user's Flickr account.

  Flickr uploads use their own API endpoint, that returns only XML.
  https://www.flickr.com/services/api/upload.api.html

  Unlike call_api_method, this uses the requests library because
  urllib2 does support multi-part POSTs on its own.

  Args:
    params (dict): the parameters to send to the API method
    file (File-like object): the image or video to upload
    token_key (string): the user's API access token
    token_secret (string): the user's API access token secret

  Return:
    dict containing the photo id (as 'id')

  Raises:
    requests.HTTPError on http error or urllib2.HTTPError if we get a
    stat='fail' response from Flickr.
  """
  upload_url = 'https://up.flickr.com/services/upload'
  auth = requests_oauthlib.OAuth1(
      client_key=appengine_config.FLICKR_APP_KEY,
      client_secret=appengine_config.FLICKR_APP_SECRET,
      resource_owner_key=token_key,
      resource_owner_secret=token_secret,
      signature_type=oauthlib.oauth1.SIGNATURE_TYPE_BODY)

  # create a request with files for signing
  faux_req = requests.Request(
    'POST', upload_url, data=params, auth=auth).prepare()
  # parse the signed parameters back out of the body
  data = urlparse.parse_qsl(faux_req.body)

  # and use them in the real request
  resp = util.requests_post(upload_url, data=data, files={'photo': file})
  logging.debug('upload response: %s, %s', resp, resp.content)
  resp.raise_for_status()

  m = re.search('<rsp stat="(\w+)">', resp.content, re.DOTALL)
  if not m:
    raise BaseException(
      'Expected response with <rsp stat="...">. Got: %s' % resp.content)

  stat = m.group(1)
  if stat == 'fail':
    m = re.search('<err code="(\d+)" msg="([\w ]+)" />', resp.content, re.DOTALL)
    if not m:
      raise BaseException(
        'Expected response with <err code="..." msg=".." />. Got: %s'
        % resp.content)
    raise_for_failure(upload_url, int(m.group(1)), m.group(2))

  m = re.search('<photoid>(\d+)</photoid>', resp.content, re.DOTALL)
  if not m:
    raise BaseException(
      'Expected response with <photoid>...</photoid>. Got: %s'
      % resp.content)

  return {'id': m.group(1)}
