"""Unit tests for instagram.py."""
from unittest.mock import patch

from flask import Flask
from webutil import util
from webutil.testutil import requests_response

from ..instagram import Callback
from . import testutil

app = Flask(__name__)
app.secret_key = 'sooper seekret'
app.add_url_rule('/callback', view_func=Callback.as_view('callback', '/done'))


class InstagramTest(testutil.TestCase):

  def setUp(self):
    super().setUp()
    self.client = app.test_client()

  @patch.object(util.session, 'post', return_value=requests_response({
    'error_type': 'OAuthException',
    'code': 400,
    'error_message': 'bad code',
  }))
  def test_callback_error_response(self, _):
    resp = self.client.get('/callback?code=my_code')
    self.assertEqual(502, resp.status_code)
