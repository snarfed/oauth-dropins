"""Unit tests for facebook.py.
"""

__author__ = ['Ryan Barrett <oauth-dropins@ryanb.org>']

import urllib2
import json

import appengine_config

from webob import exc

import facebook
import handlers
from webutil import util
from webutil import testutil


class FacebookTest(testutil.HandlerTest):

  def setUp(self):
    super(FacebookTest, self).setUp()
    self.auth = facebook.FacebookAuth(id='123', type='user',
                                      access_token_str='token')

  def test_urlopen_batch(self):
    self.expect_urlopen(
      facebook.API_BATCH_URL,
      data='batch=[{"method":"GET","relative_url":"abc"},'
                  '{"method":"GET","relative_url":"def"}]',
      response=json.dumps([{'code': 200, 'body': '{"abc": 1}'},
                           {'code': 200, 'body': '{"def": 2}'}]))
    self.mox.ReplayAll()

    self.assert_equals(({'abc': 1}, {'def': 2}),
                       self.auth.urlopen_batch(('abc', 'def')))

  def test_urlopen_batch_error(self):
    self.expect_urlopen(
      facebook.API_BATCH_URL,
      data='batch=[{"method":"GET","relative_url":"abc"},'
                  '{"method":"GET","relative_url":"def"}]',
      response=json.dumps([{'code': 200},
                           {'code': 499, 'body': 'error body'}]))
    self.mox.ReplayAll()

    try:
      self.auth.urlopen_batch(('abc', 'def'))
      assert False, 'expected HTTPError'
    except urllib2.HTTPError, e:
      self.assertEqual(499, e.code)
      self.assertEqual('error body', e.reason)
