"""App Engine settings.

Reads Facebook and Twitter app keys and secrets into constants from these files:

dropbox_app_key
dropbox_app_secret
facebook_app_id
facebook_app_secret
facebook_app_id_local
facebook_app_secret_local
google_client_id
google_client_secret
instagram_client_id
instagram_client_secret
instagram_client_id_local
instagram_client_secret_local
twitter_app_key
twitter_app_secret
"""

import os


# app_identity.get_default_version_hostname() would be better here, but
# it doesn't work in dev_appserver since that doesn't set
# os.environ['DEFAULT_VERSION_HOSTNAME'].
HOST = os.getenv('HTTP_HOST')
SCHEME = 'https' if (os.getenv('HTTPS') == 'on') else 'http'


def read(filename):
  """Returns the contents of filename, or None if it doesn't exist."""
  if os.path.exists(filename):
    with open(filename) as f:
      return f.read().strip()

DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Development')

if DEBUG:
  FACEBOOK_APP_ID = read('facebook_app_id_local')
  FACEBOOK_APP_SECRET = read('facebook_app_secret_local')
  INSTAGRAM_CLIENT_ID = read('instagram_client_id_local')
  INSTAGRAM_CLIENT_SECRET = read('instagram_client_secret_local')
else:
  FACEBOOK_APP_ID = read('facebook_app_id')
  FACEBOOK_APP_SECRET = read('facebook_app_secret')
  INSTAGRAM_CLIENT_ID = read('instagram_client_id')
  INSTAGRAM_CLIENT_SECRET = read('instagram_client_secret')

DROPBOX_APP_KEY = read('dropbox_app_key')
DROPBOX_APP_SECRET = read('dropbox_app_secret')
GOOGLE_CLIENT_ID = read('google_client_id')
GOOGLE_CLIENT_SECRET = read('google_client_secret')
TWITTER_APP_KEY = read('twitter_app_key')
TWITTER_APP_SECRET = read('twitter_app_secret')
