"""Unit tests for bluesky.py."""
from requests_oauth2client import (
  DPoPKey,
  DPoPToken,
  OAuth2AccessTokenAuth,
  OAuth2Client,
  TokenSerializer,
)

from ..bluesky import BlueskyAuth, make_session_callback
from . import testutil


class BlueskyTest(testutil.TestCase):

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
