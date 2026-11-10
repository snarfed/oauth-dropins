"""Unit tests for twitter.py."""
from unittest.mock import patch

from flask import Flask
import requests
from webutil.testutil import requests_response

from .. import twitter_auth
from ..twitter import Start
from . import testutil

app = Flask(__name__)
app.add_url_rule('/start', view_func=Start.as_view('start', '/callback'),
                 methods=['POST'])


@patch.object(twitter_auth, 'TWITTER_APP_KEY', 'app_key')
@patch.object(twitter_auth, 'TWITTER_APP_SECRET', 'app_secret')
class TwitterTest(testutil.TestCase):

  @patch.object(requests.Session, 'request', return_value=requests_response(
    '<errors><error code="415">Callback URL not approved</error></errors>',
    status=403))
  def test_start_request_token_fails(self, _):
    resp = app.test_client().post('/start')
    self.assertEqual(502, resp.status_code)
    self.assertIn('Callback URL not approved', resp.get_data(as_text=True))
