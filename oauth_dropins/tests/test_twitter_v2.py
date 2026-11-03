"""Unit tests for twitter_v2.py."""
from webutil.util import json_dumps, json_loads

from ..twitter_v2 import TwitterOAuth2
from . import testutil


class TwitterV2Test(testutil.TestCase):

  def test_session_no_refresh_token(self):
    auth = TwitterOAuth2(id='alice', user_json='{}',
                         token_json=json_dumps({'access_token': 'towkin'}))
    self.assertEqual('towkin', auth.session().token['access_token'])

  def test_session_refresh_stores_token(self):
    auth = TwitterOAuth2(id='alice', user_json='{}', token_json=json_dumps({
      'access_token': 'towkin',
      'refresh_token': 'reephrush',
      'expires_at': 1,
    }))
    auth.put()

    new_token = {'access_token': 'nu_towkin', 'refresh_token': 'nu_reephrush'}
    auth.session().token_updater(new_token)

    self.assertEqual(new_token, json_loads(auth.key.get().token_json))
