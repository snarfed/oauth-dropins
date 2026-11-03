"""Unit tests for mastodon.py."""
from unittest.mock import patch

from flask import Flask
from webutil import util
from webutil.testutil import requests_response
from webutil.util import json_dumps

from ..mastodon import Callback, MastodonApp, MastodonAuth, MastodonLogin
from . import testutil

USER = {
  'id': '123',
  'username': 'alice',
  'uri': 'https://mastodon.social/users/alice',
}

app = Flask(__name__)
app.secret_key = 'sooper seekret'
app.add_url_rule('/callback', view_func=Callback.as_view('callback', '/done'))


class MastodonTest(testutil.TestCase):

  def setUp(self):
    super().setUp()
    self.client = app.test_client()
    self.app = MastodonApp(instance='https://mastodon.social/', data=json_dumps({
      'client_id': 'cli_id',
      'client_secret': 'cli_seekret',
    }))
    self.app.put()

  def callback(self, status):
    login = MastodonLogin(app=self.app.key, state='foo').put()
    resp = self.client.get(f'/callback?code=my_code&state={login.id()}')
    self.assertEqual(status, resp.status_code, resp.get_data(as_text=True))
    return resp

  @patch.object(util.session, 'post', return_value=requests_response({
    'access_token': 'towkin',
  }))
  @patch.object(util.session, 'get', return_value=requests_response(USER))
  def test_callback(self, *_):
    resp = self.callback(302)
    self.assertTrue(resp.headers['Location'].startswith('/done?'))

    auth = MastodonAuth.get_by_id('@alice@mastodon.social')
    self.assertEqual('https://mastodon.social/users/alice', auth.actor_id())
    self.assertEqual('towkin', auth.access_token_str)

  @patch.object(util.session, 'post', return_value=requests_response({
    'access_token': 'towkin',
  }))
  @patch.object(util.session, 'get', return_value=requests_response({
    **USER,
    'uri': 'https://other.social/users/alice',
  }))
  def test_callback_uri_on_other_host(self, *_):
    self.callback(400)
    self.assertIsNone(MastodonAuth.get_by_id('@alice@mastodon.social'))
