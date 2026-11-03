"""Unit tests for threads.py."""
from webutil.util import json_dumps, json_loads

from ..threads import ThreadsAuth
from . import testutil


class ThreadsTest(testutil.TestCase):

  def test_session_refresh_stores_token(self):
    auth = ThreadsAuth(id='alice', user_json='{}', token_json=json_dumps({
      'access_token': 'towkin',
      'refresh_token': 'reephrush',
      'expires_at': 1,
    }))
    auth.put()

    new_token = {'access_token': 'nu_towkin', 'refresh_token': 'nu_reephrush'}
    auth.session().token_updater(new_token)

    self.assertEqual(new_token, json_loads(auth.key.get().token_json))
