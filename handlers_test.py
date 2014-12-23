"""Unit tests for handlers.py.
"""

__author__ = ['Ryan Barrett <oauth-dropins@ryanb.org>']

import StringIO
import urllib2

import appengine_config

import apiclient.errors
import httplib2
from oauth2client.client import AccessTokenRefreshError
from python_instagram.bind import InstagramAPIError
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
        urllib2.HTTPError('url', 429, 'msg', {},  StringIO.StringIO('my body'))))
    self.assertEquals((None, 'foo bar'), ihc(urllib2.URLError('foo bar')))

    self.assertEquals(('429', 'my body'), ihc(
        requests.HTTPError(response=util.Struct(status_code='429', text='my body'))))

    self.assertEquals((None, None), ihc(AccessTokenRefreshError('invalid_foo')))
    self.assertEquals(('401', None), ihc(AccessTokenRefreshError('invalid_grant')))

    self.assertEquals(('429', 'my desc: my body'), ihc(
        InstagramAPIError('429', 'my desc', 'my body')))
    self.assertEquals(('401', 'OAuthAccessTokenException: my body'), ihc(
        InstagramAPIError('422', 'OAuthAccessTokenException', 'my body')))
    self.assertEquals(('401', 'APIRequiresAuthenticationError: my body'), ihc(
        InstagramAPIError('400', 'APIRequiresAuthenticationError', 'my body')))
