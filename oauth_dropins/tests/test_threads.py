"""Unit tests for threads.py."""
from unittest.mock import ANY, patch
import urllib.parse

from flask import Flask
from requests_oauth2client import BearerToken, ClientSecretPost
from webutil import util
from webutil.testutil import requests_response
from webutil.util import json_dumps, json_loads

from .. import threads
from ..threads import Callback, Start, ThreadsAuth
from . import testutil

USER = {
  'id': '123',
  'username': 'alice',
  'name': 'Alice',
}

app = Flask(__name__)
app.secret_key = 'sooper seekret'
app.add_url_rule('/start', view_func=Start.as_view('start', '/callback'),
                 methods=['POST'])
app.add_url_rule('/callback', view_func=Callback.as_view('callback', '/done'))


@patch.object(threads, 'APP_ID', 'app_id')
@patch.object(threads, 'APP_SECRET', 'app_secret')
class ThreadsTest(testutil.TestCase):

  def setUp(self):
    super().setUp()
    self.client = app.test_client()

  def test_start(self):
    resp = self.client.post('/start', data={'state': 'foo'})
    self.assertEqual(302, resp.status_code)

    url = urllib.parse.urlparse(resp.headers['Location'])
    self.assertEqual('https://threads.net/oauth/authorize',
                     url._replace(query='').geturl())
    self.assertEqual({
      'client_id': ['app_id'],
      'redirect_uri': ['http://localhost/callback'],
      'response_type': ['code'],
      'scope': ['threads_basic'],
      'state': ['foo'],
    }, urllib.parse.parse_qs(url.query))

  @patch.object(util.session, 'request', return_value=requests_response({
    'access_token': 'towkin',
    'user_id': 123,
  }))
  @patch.object(util.session, 'get', return_value=requests_response(USER))
  def test_callback(self, mock_get, mock_request):
    resp = self.client.get('/callback?code=my_code&state=foo')
    self.assertEqual(302, resp.status_code, resp.get_data(as_text=True))

    mock_request.assert_called_once_with(
      'POST', 'https://graph.threads.net/oauth/access_token', data={
        'grant_type': 'authorization_code',
        'code': 'my_code',
        'redirect_uri': 'http://localhost/callback',
      }, auth=ClientSecretPost('app_id', 'app_secret'), timeout=10,
      headers={'Accept': 'application/json'})
    mock_get.assert_called_once_with(threads.API_ACCOUNT_URL, auth=ANY,
                                     timeout=ANY, stream=ANY, headers=ANY)
    self.assertEqual('towkin', mock_get.call_args.kwargs['auth'].access_token)

    auth = ThreadsAuth.get_by_id('123')
    self.assertEqual({'access_token': 'towkin', 'token_type': 'Bearer',
                      'user_id': 123}, json_loads(auth.token_json))
    self.assertEqual(USER, json_loads(auth.user_json))
    self.assertEqual('towkin', auth.access_token())
    self.assertEqual(
      f'/done?auth_entity={auth.key.urlsafe().decode()}&state=foo&access_token=towkin',
      resp.headers['Location'])

  def test_callback_declined(self):
    resp = self.client.get('/callback?error=access_denied&state=foo')
    self.assertEqual(302, resp.status_code)
    self.assertEqual('/done?declined=True', resp.headers['Location'])

  def test_session(self):
    auth = ThreadsAuth(id='123', user_json='{}',
                       token_json=json_dumps({'access_token': 'towkin'}))
    self.assertEqual(BearerToken('towkin'), auth.session().auth)
