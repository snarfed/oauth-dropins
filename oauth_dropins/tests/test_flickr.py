"""Unit tests for flickr.py."""
from flask import Flask

from ..flickr import Callback
from . import testutil

app = Flask(__name__)
app.secret_key = 'sooper seekret'
app.add_url_rule('/callback', view_func=Callback.as_view('callback', '/done'))


class FlickrTest(testutil.TestCase):

  def setUp(self):
    super().setUp()
    self.client = app.test_client()

  def test_callback_unknown_oauth_token(self):
    resp = self.client.get('/callback?oauth_token=nope&oauth_verifier=ver')
    self.assertEqual(400, resp.status_code)
