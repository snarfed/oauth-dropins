"""Unit tests for patreon.py."""
from unittest.mock import ANY, patch
import urllib.parse

from flask import Flask
from requests_oauth2client import BearerToken, ClientSecretPost
from webutil import util
from webutil.testutil import requests_response
from webutil.util import json_dumps, json_loads

from .. import patreon
from ..patreon import Callback, Membership, parse_membership, PatreonAuth, Start
from . import testutil

USER = {
  'data': {
    'id': '123',
    'type': 'user',
    'attributes': {
      'full_name': 'Alice',
      'image_url': 'http://alice.example/pic.jpg',
      'url': 'https://www.patreon.com/alice',
      'vanity': 'alice',
    },
    'relationships': {
      'memberships': {
        'data': [{'id': 'abc-def', 'type': 'member'}],
      },
    },
  },
  'included': [{
    'id': 'abc-def',
    'type': 'member',
    'attributes': {
      'patron_status': 'active_patron',
      'currently_entitled_amount_cents': 500,
    },
  }],
}

app = Flask(__name__)
app.secret_key = 'sooper seekret'
app.add_url_rule('/start', view_func=Start.as_view('start', '/callback'),
                 methods=['POST'])
app.add_url_rule('/callback', view_func=Callback.as_view('callback', '/done'))


@patch.object(patreon, 'CLIENT_ID', 'client_id')
@patch.object(patreon, 'CLIENT_SECRET', 'client_secret')
class PatreonTest(testutil.TestCase):

  def setUp(self):
    super().setUp()
    self.client = app.test_client()

  def test_start(self):
    resp = self.client.post('/start', data={'state': 'foo'})
    self.assertEqual(302, resp.status_code)

    url = urllib.parse.urlparse(resp.headers['Location'])
    self.assertEqual('https://www.patreon.com/oauth2/authorize',
                     url._replace(query='').geturl())
    self.assertEqual({
      'client_id': ['client_id'],
      'redirect_uri': ['http://localhost/callback'],
      'response_type': ['code'],
      'scope': ['identity'],
      'state': ['foo'],
    }, urllib.parse.parse_qs(url.query))

  @patch.object(util.session, 'request', return_value=requests_response({
    'access_token': 'towkin',
    'refresh_token': 'reephrush',
    'expires_in': 2678400,
    'scope': 'identity',
    'token_type': 'Bearer',
  }))
  @patch.object(util.session, 'get', return_value=requests_response(USER))
  def test_callback(self, mock_get, mock_request):
    resp = self.client.get('/callback?code=my_code&state=foo')
    self.assertEqual(302, resp.status_code, resp.get_data(as_text=True))

    mock_request.assert_called_once_with(
      'POST', 'https://www.patreon.com/api/oauth2/token', data={
        'grant_type': 'authorization_code',
        'code': 'my_code',
        'redirect_uri': 'http://localhost/callback',
      }, auth=ClientSecretPost('client_id', 'client_secret'), timeout=10,
      headers={'Accept': 'application/json'})
    mock_get.assert_called_once_with(patreon.API_IDENTITY_URL, auth=ANY,
                                     timeout=ANY, stream=ANY, headers=ANY)
    self.assertEqual('towkin', mock_get.call_args.kwargs['auth'].access_token)

    auth = PatreonAuth.get_by_id('123')
    self.assertEqual({
      'access_token': 'towkin',
      'refresh_token': 'reephrush',
      'expires_in': 2678400,
      'scope': 'identity',
      'token_type': 'Bearer',
    }, json_loads(auth.token_json))
    self.assertEqual(USER, json_loads(auth.user_json))
    self.assertEqual('towkin', auth.access_token())
    self.assertEqual('reephrush', auth.refresh_token)
    self.assertEqual('Alice', auth.user_display_name())
    self.assertEqual('http://alice.example/pic.jpg', auth.image_url())
    self.assertEqual('https://www.patreon.com/alice', auth.user_url())
    self.assertEqual(
      f'/done?auth_entity={auth.key.urlsafe().decode()}&state=foo&access_token=towkin&refresh_token=reephrush',
      resp.headers['Location'])

  def test_callback_declined(self):
    resp = self.client.get('/callback?error=access_denied&state=foo')
    self.assertEqual(302, resp.status_code)
    self.assertEqual('/done?declined=True', resp.headers['Location'])

  def test_session(self):
    auth = PatreonAuth(id='123', user_json='{}',
                       token_json=json_dumps({'access_token': 'towkin'}))
    self.assertEqual(BearerToken('towkin'), auth.session().auth)

  def test_parse_membership(self):
    for expected, attrs in (
        (Membership.PAID, {'patron_status': 'active_patron',
                           'currently_entitled_amount_cents': 500}),
        (Membership.FREE, {'patron_status': 'active_patron',
                           'currently_entitled_amount_cents': 0}),
        (Membership.FORMER, {'patron_status': 'declined_patron',
                             'currently_entitled_amount_cents': 500}),
        (Membership.FORMER, {'patron_status': 'former_patron'}),
        (None, {'patron_status': None}),
        (None, {}),
        (None, None),
    ):
      with self.subTest(attrs=attrs):
        self.assertEqual(expected, parse_membership(attrs))

  def test_get_membership(self):
    for expected, member in (
        (Membership.PAID, {'patron_status': 'active_patron',
                           'currently_entitled_amount_cents': 500}),
        (None, None),
    ):
      with self.subTest(member=member):
        user = {'data': {'id': '123'}}
        if member:
          user['included'] = [{'type': 'member', 'attributes': member}]
        auth = PatreonAuth(id='123', token_json='{}', user_json=json_dumps(user))
        self.assertEqual(expected, auth.get_membership())
