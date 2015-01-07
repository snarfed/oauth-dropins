"""Unit tests for handlers.py.
"""

__author__ = ['Ryan Barrett <oauth-dropins@ryanb.org>']

import StringIO
import urllib2
import json

import apiclient.errors
import httplib2
from oauth2client.client import AccessTokenRefreshError
import requests
from webob import exc

import handlers
from webutil import util
from webutil import testutil


class HandlersTest(testutil.HandlerTest):

  def test_interpret_http_exception(self):
    ihc = handlers.interpret_http_exception

    self.assertEquals(('402', '402 Payment Required\n\nmy body'), ihc(
        exc.HTTPPaymentRequired(body_template='my body')))
    self.assertEquals(('429', 'my body'), ihc(
        apiclient.errors.HttpError(httplib2.Response({'status': 429}), 'my body')))
    self.assertEquals(('429', 'my body'), ihc(
        urllib2.HTTPError('url', 429, 'msg', {}, StringIO.StringIO('my body'))))
    self.assertEquals((None, 'foo bar'), ihc(urllib2.URLError('foo bar')))

    self.assertEquals(('429', 'my body'), ihc(
        requests.HTTPError(response=util.Struct(status_code='429', text='my body'))))

    self.assertEquals((None, None), ihc(AccessTokenRefreshError('invalid_foo')))
    self.assertEquals(('401', None), ihc(AccessTokenRefreshError('invalid_grant')))

    # this is the type of response we get back from instagram
    ig_token_error = json.dumps({
      "meta": {
        "error_type": "OAuthAccessTokenException",
        "code": 400,
        "error_message": "The access_token provided is invalid."
      }
    })

    self.assertEquals(('400', ig_token_error), ihc(urllib2.HTTPError(
      'url', 400, 'BAD REQUEST', {}, StringIO.StringIO(ig_token_error))))
