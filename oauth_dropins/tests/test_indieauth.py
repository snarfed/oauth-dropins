"""Unit tests for indieauth.py."""
from unittest.mock import patch
from urllib.parse import parse_qs, parse_qsl, urlparse

from flask import Flask
from webutil import util
from webutil.testutil import requests_response
from webutil.util import json_dumps, json_loads

from ..indieauth import (
  Callback,
  IndieAuth,
  INDIELOGIN_CLIENT_ID,
  INDIELOGIN_ISSUER,
  INDIELOGIN_TOKEN_URL,
  INDIELOGIN_URL,
  Start,
)
from ..models import PkceCode
from ..views import LOGINS_SESSION_KEY
from . import testutil

AUTH_ENDPOINT_ONLY = """
<html><head><link rel="authorization_endpoint" href="http://auth/"></head></html>
"""
AUTH_AND_TOKEN_ENDPOINTS = """
<html><head>
<link rel="authorization_endpoint" href="http://auth/">
<link rel="token_endpoint" href="http://token/">
</head></html>
"""

app = Flask(__name__)
app.secret_key = 'sooper seekret'
app.add_url_rule('/start',view_func=Start.as_view('start', '/callback'),
                 methods=['POST'])
app.add_url_rule('/callback', view_func=Callback.as_view('callback', '/done'))


class IndieAuthTest(testutil.TestCase):

  def setUp(self):
    super().setUp()
    self.client = app.test_client()
    self.post_headers = {
      'Accept': 'application/json',
      'User-Agent': util.user_agent,
    }

  def assert_post(self, mock_post, url, data):
    mock_post.assert_called_once_with(url, data=data, headers=self.post_headers,
                                      stream=True, timeout=util.HTTP_TIMEOUT)

  def callback(self, status=302, iss=INDIELOGIN_ISSUER, **stored):
    stored = {
      'auth_endpoint': INDIELOGIN_URL,
      'token_endpoint': INDIELOGIN_TOKEN_URL,
      **stored,
    }
    PkceCode(id='my_state', verifier='my_verifier', challenge='my_challenge',
             me='http://snarfed.org', state='towkin', **stored).put()
    resp = self.client.get('/callback', query_string={
      'code': 'my_code',
      'state': 'my_state',
      'iss': iss,
    })
    self.assertEqual(status, resp.status_code, resp.get_data(as_text=True))
    return resp

  def check_start(self, expected_endpoint, expected_token_endpoint):
    resp = self.client.post('/start', data={
      'me': 'http://snarfed.org',
      'state': 'foo',
    })
    self.assertEqual(302, resp.status_code)

    url, query = resp.headers['Location'].split('?')
    self.assertEqual(expected_endpoint, url)

    params = dict(parse_qsl(query))
    stored = PkceCode.get_by_id(params['state'])
    self.assertEqual({
      'me': 'http://snarfed.org',
      'client_id': INDIELOGIN_CLIENT_ID,
      'redirect_uri': 'http://localhost/callback',
      'code_challenge': stored.challenge,
      'code_challenge_method': 'S256',
      'response_type': 'code',
      'scope': 'profile',
      'state': stored.key.id(),
    }, params)
    self.assertEqual(expected_token_endpoint, stored.token_endpoint)

  @patch.object(util.session, 'get', return_value=requests_response(''))
  def test_start_default_endpoints(self, _):
    self.check_start(INDIELOGIN_URL, INDIELOGIN_TOKEN_URL)

  @patch.object(util.session, 'get', return_value=requests_response('', status=500))
  def test_start_site_fetch_fails(self, _):
    self.check_start(INDIELOGIN_URL, INDIELOGIN_TOKEN_URL)

  @patch.object(util.session, 'get', return_value=requests_response(AUTH_ENDPOINT_ONLY))
  def test_start_auth_endpoint_only(self, _):
    self.check_start('http://auth/', None)

  @patch.object(util.session, 'get', return_value=requests_response("""
<html><head><link rel="token_endpoint" href="http://token/"></head></html>
"""))
  def test_start_token_endpoint_only(self, _):
    self.check_start(INDIELOGIN_URL, INDIELOGIN_TOKEN_URL)

  @patch.object(util.session, 'get', return_value=requests_response(AUTH_AND_TOKEN_ENDPOINTS))
  def test_start_auth_and_token_endpoints(self, _):
    self.check_start('http://auth/', 'http://token/')

  @patch.object(util.session, 'get', return_value=requests_response(AUTH_AND_TOKEN_ENDPOINTS))
  def test_start_stores_state(self, _):
    resp = self.client.post('/start', data={
      'me': 'http://snarfed.org',
      'state': 'foo',
    })
    self.assertEqual(302, resp.status_code)

    location = resp.headers['Location']
    state = parse_qs(urlparse(location).query)['state'][0]
    stored = PkceCode.get_by_id(state)
    self.assertEqual('http://auth/', stored.auth_endpoint)
    self.assertEqual('http://token/', stored.token_endpoint)
    self.assertEqual('http://snarfed.org', stored.me)
    self.assertEqual('foo', stored.state)
    self.assertNotIn(stored.verifier, location)

  @patch.object(util.session, 'post', return_value=requests_response(json_dumps({
    'me': 'http://snarfed.org',
    'access_token': 'a_towkin',
    'refresh_token': 'r_towkin',
  })))
  @patch.object(util.session, 'get', return_value=requests_response(''))
  def test_callback(self, mock_get, mock_post):
    resp = self.callback()

    self.assert_post(mock_post, INDIELOGIN_TOKEN_URL, {
      'grant_type': 'authorization_code',
      'code': 'my_code',
      'client_id': INDIELOGIN_CLIENT_ID,
      'redirect_uri': 'http://localhost/callback',
      'code_verifier': 'my_verifier',
    })
    self.assertEqual(['http://snarfed.org'],
                     [c.args[0] for c in mock_get.call_args_list])

    auth = IndieAuth.get_by_id('http://snarfed.org')
    self.assertEqual('a_towkin', auth.access_token_str)
    self.assertEqual('r_towkin', auth.refresh_token_str)
    self.assertEqual('http://snarfed.org', json_loads(auth.user_json)['me'])

    self.assertEqual({
      'auth_entity': [auth.key.urlsafe().decode()],
      'state': ['towkin'],
      'access_token': ['a_towkin'],
    }, parse_qs(urlparse(resp.headers['Location']).query))

    with self.client.session_transaction() as session:
      self.assertEqual([('IndieAuth', 'http://snarfed.org')],
                       session[LOGINS_SESSION_KEY])

  @patch.object(util.session, 'post', return_value=requests_response('me=http://snarfed.org'))
  @patch.object(util.session, 'get', return_value=requests_response(''))
  def test_callback_auth_endpoint_only(self, _, mock_post):
    self.callback(auth_endpoint='http://auth/', token_endpoint=None, iss=None)
    self.assert_post(mock_post, 'http://auth/', {
      'grant_type': 'authorization_code',
      'code': 'my_code',
      'client_id': INDIELOGIN_CLIENT_ID,
      'redirect_uri': 'http://localhost/callback',
      'code_verifier': 'my_verifier',
      'me': 'http://snarfed.org',
      'state': 'towkin',
    })

  @patch.object(util.session, 'post')
  def test_callback_missing_iss(self, mock_post):
    self.callback(status=400, iss=None)
    mock_post.assert_not_called()

  @patch.object(util.session, 'post')
  def test_callback_wrong_iss(self, mock_post):
    self.callback(status=400, iss='http://evil/')
    mock_post.assert_not_called()

  @patch.object(util.session, 'post')
  def test_callback_forged_state(self, mock_post):
    state = util.encode_oauth_state({
      'token_endpoint': 'http://evil/token',
      'me': 'http://snarfed.org',
      'state': 'towkin',
    })
    resp = self.client.get(f'/callback?code=my_code&state={state}')
    self.assertEqual(400, resp.status_code)

    mock_post.assert_not_called()
    self.assertEqual([], IndieAuth.query().fetch())

  @patch.object(util.session, 'post', return_value=requests_response('me=http://snarfed.org'))
  @patch.object(util.session, 'get', return_value=requests_response(''))
  def test_callback_state_is_single_use(self, *_):
    self.callback()
    self.assertIsNone(PkceCode.get_by_id('my_state'))

    resp = self.client.get('/callback', query_string={
      'code': 'my_code',
      'state': 'my_state',
      'iss': INDIELOGIN_ISSUER,
    })
    self.assertEqual(400, resp.status_code)

  @patch.object(util.session, 'post', return_value=requests_response('me=http://other.org'))
  @patch.object(util.session, 'get', return_value=requests_response(''))
  def test_callback_different_me_same_endpoints(self, *_):
    self.callback()
    self.assertEqual(['http://other.org'],
                     [a.key.id() for a in IndieAuth.query()])

  @patch.object(util.session, 'post', return_value=requests_response('me=http://other.org'))
  @patch.object(util.session, 'get', return_value=requests_response("""
<html><head><link rel="authorization_endpoint" href="http://other/auth"></head></html>
"""))
  def test_callback_different_me_different_auth_endpoint(self, *_):
    self.callback(status=400)
    self.assertEqual([], IndieAuth.query().fetch())

  @patch.object(util.session, 'post', return_value=requests_response('me=http://other.org'))
  @patch.object(util.session, 'get', return_value=requests_response(AUTH_ENDPOINT_ONLY))
  def test_callback_different_me_auth_endpoint_only(self, *_):
    self.callback(auth_endpoint='http://auth/', token_endpoint=None)
    self.assertEqual(['http://other.org'],
                     [a.key.id() for a in IndieAuth.query()])

  @patch.object(util.session, 'post', return_value=requests_response('me=http://other.org'))
  @patch.object(util.session, 'get', return_value=requests_response(AUTH_AND_TOKEN_ENDPOINTS))
  def test_callback_different_me_different_token_endpoint(self, *_):
    self.callback(status=400, auth_endpoint='http://auth/',
                  token_endpoint='http://evil/token')
    self.assertEqual([], IndieAuth.query().fetch())
