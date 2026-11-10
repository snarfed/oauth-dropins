"""Unit tests for twitter_v2.py."""
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from flask import Flask
from requests_oauth2client import PkceUtils
from webutil.util import json_dumps, json_loads

from .. import twitter_v2
from ..models import PkceCode
from ..twitter_v2 import Start, TwitterOAuth2
from . import testutil

app = Flask(__name__)
app.add_url_rule('/start', view_func=Start.as_view('start', '/callback'),
                 methods=['POST'])


@patch.object(twitter_v2, 'TWITTER_CLIENT_ID', 'client_id')
@patch.object(twitter_v2, 'TWITTER_CLIENT_SECRET', 'client_secret')
class TwitterV2Test(testutil.TestCase):

  def test_start(self):
    resp = app.test_client().post('/start', data={'state': 'foo'})
    self.assertEqual(302, resp.status_code)

    location = resp.headers['Location']
    url = urlparse(location)
    self.assertEqual('https://twitter.com/i/oauth2/authorize',
                     url._replace(query='').geturl())

    stored = PkceCode.get_by_id('foo')
    self.assertEqual({
      'client_id': ['client_id'],
      'redirect_uri': ['http://localhost/callback'],
      'response_type': ['code'],
      'scope': ['tweet.read users.read'],
      'state': ['foo'],
      'code_challenge': [PkceUtils.derive_challenge(stored.verifier)],
      'code_challenge_method': ['S256'],
    }, parse_qs(url.query))
    self.assertNotIn(stored.verifier, location)

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
