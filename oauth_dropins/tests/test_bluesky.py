"""Unit tests for bluesky.py."""
from unittest.mock import patch

from flask import Flask
from requests_oauth2client import (
  DPoPKey,
  DPoPToken,
  OAuth2AccessTokenAuth,
  OAuth2Client,
  TokenSerializer,
)
from webutil import util
from webutil.testutil import requests_response

from ..bluesky import BlueskyAuth, make_session_callback, PasswordCallback
from . import testutil

DID_DOC = {
  'id': 'did:plc:alice',
  'service': [{
    'id': '#atproto_pds',
    'type': 'AtprotoPersonalDataServer',
    'serviceEndpoint': 'https://pds.alice/',
  }],
}
SESSION = {
  'did': 'did:plc:alice',
  'handle': 'alice.com',
  'accessJwt': 'towkin',
  'refreshJwt': 'reephrush',
}
PROFILE = {
  'did': 'did:plc:alice',
  'handle': 'alice.com',
}

app = Flask(__name__)
app.secret_key = 'sooper seekret'
app.add_url_rule('/callback', methods=['POST'],
                 view_func=PasswordCallback.as_view('callback', '/done'))


class BlueskyTest(testutil.TestCase):

  def setUp(self):
    super().setUp()
    self.client = app.test_client()

  def password_callback(self, status):
    resp = self.client.post('/callback', data={
      'username': 'alice.com',
      'password': 'passwerd',
    })
    self.assertEqual(status, resp.status_code, resp.get_data(as_text=True))
    return resp

  @patch('arroba.did.resolve_handle', return_value='did:plc:alice')
  @patch('arroba.did.resolve', return_value=DID_DOC)
  @patch.object(util.session, 'post', return_value=requests_response(SESSION))
  @patch.object(util.session, 'get', return_value=requests_response(PROFILE))
  def test_password_callback(self, *_):
    resp = self.password_callback(302)
    self.assertTrue(resp.headers['Location'].startswith('/done?'))

    auth = BlueskyAuth.get_by_id('did:plc:alice')
    self.assertEqual('https://pds.alice/', auth.pds_url)
    self.assertEqual('passwerd', auth.password)
    self.assertEqual(SESSION, auth.session)

  @patch('arroba.did.resolve_handle', return_value='did:plc:alice')
  @patch('arroba.did.resolve', return_value=DID_DOC)
  @patch.object(util.session, 'post', return_value=requests_response({
    **SESSION,
    'did': 'did:plc:eve',
  }))
  @patch.object(util.session, 'get', return_value=requests_response(PROFILE))
  def test_password_callback_session_other_did(self, *_):
    self.password_callback(302)
    self.assertIsNone(BlueskyAuth.get_by_id('did:plc:alice'))
    self.assertIsNone(BlueskyAuth.get_by_id('did:plc:eve'))

  @patch('arroba.did.resolve_handle', return_value='did:plc:alice')
  @patch('arroba.did.resolve', return_value=DID_DOC)
  @patch.object(util.session, 'post', return_value=requests_response(SESSION))
  @patch.object(util.session, 'get', return_value=requests_response({
    **PROFILE,
    'did': 'did:plc:eve',
  }))
  def test_password_callback_profile_other_did(self, *_):
    self.password_callback(400)
    self.assertIsNone(BlueskyAuth.get_by_id('did:plc:alice'))
    self.assertIsNone(BlueskyAuth.get_by_id('did:plc:eve'))

  def test_app_password_session(self):
    auth_entity = BlueskyAuth(id='did:plc:alice', pds_url='https://bsky.social',
                              user_json='{}', session={'accessJwt': 'towkin'})
    auth_entity.put()

    make_session_callback(auth_entity)({'accessJwt': 'nu_towkin'})

    self.assertEqual({'accessJwt': 'nu_towkin'}, auth_entity.key.get().session)

  def test_dpop_token(self):
    dpop_token = DPoPToken(access_token='towkin', _dpop_key=DPoPKey.generate())
    auth_entity = BlueskyAuth(id='did:plc:alice', pds_url='https://bsky.social',
                              user_json='{}',
                              dpop_token=TokenSerializer().dumps(dpop_token))
    auth_entity.put()

    new_token = DPoPToken(access_token='nu_towkin', _dpop_key=DPoPKey.generate())
    client = OAuth2Client(token_endpoint='https://un/used', client_id='unused',
                          client_secret='unused')
    make_session_callback(auth_entity)(
      OAuth2AccessTokenAuth(client=client, token=new_token))

    self.assertEqual(new_token,
                     TokenSerializer().loads(auth_entity.key.get().dpop_token))
