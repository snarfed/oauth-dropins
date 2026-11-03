"""Unit tests for disqus.py."""
from flask import Flask

from ..disqus import Callback
from . import testutil

app = Flask(__name__)
app.secret_key = 'sooper seekret'
app.add_url_rule('/callback', view_func=Callback.as_view('callback', '/done'))


class DisqusTest(testutil.TestCase):

  def setUp(self):
    super().setUp()
    self.client = app.test_client()

  def test_callback_declined(self):
    resp = self.client.get('/callback?error=access_denied&state=foo')
    self.assertEqual(302, resp.status_code)
    self.assertEqual('/done?declined=True', resp.headers['Location'])
