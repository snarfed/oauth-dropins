"""Unit test utilities."""
import requests
from webutil import testutil
from webutil.appengine_config import ndb_client


class TestCase(testutil.TestCase):
  """Base test case. Resets the datastore emulator and opens an ndb context."""
  def setUp(self):
    super().setUp()

    requests.post('http://0.0.0.0:8089/reset').raise_for_status()

    self.ndb_context = ndb_client.context()
    self.ndb_context.__enter__()

  def tearDown(self):
    self.ndb_context.__exit__(None, None, None)
