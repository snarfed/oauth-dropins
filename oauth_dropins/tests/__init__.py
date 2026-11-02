import io, logging, os, sys

from webutil.appengine_info import DEBUG

assert DEBUG
creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
assert not creds or creds.endswith('fake_user_account.json')

logging.getLogger('chardet').setLevel(logging.INFO)
logging.getLogger('google.cloud').setLevel(logging.INFO)
logging.getLogger('urllib3').setLevel(logging.INFO)

# Piggyback on unittest's -v and -q flags to show/hide logging.
logging.basicConfig()
if '-v' in sys.argv:
  logging.getLogger().setLevel(logging.DEBUG)
else:
  # don't emit logs. do this instead of setLevel() or disable() so that the log
  # messages still get evaluated and raise the same exceptions that they would if
  # they got emitted.
  handler = logging.getLogger().handlers[0]
  if hasattr(handler, 'setStream'):
    handler.setStream(io.StringIO())
