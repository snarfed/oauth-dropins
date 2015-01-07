"""App Engine settings.

Reads app keys and secrets into constants from these files:

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
tumblr_app_key
tumblr_app_secret
wordpress_client_id
wordpress_client_secret
wordpress_client_id_local
wordpress_client_secret_local
"""

import os
import sys

from webutil.appengine_config import *

# default timeout. the G+ and Instagram APIs use httplib2, which honors this.
import socket
socket.setdefaulttimeout(HTTP_TIMEOUT)
# monkey-patch socket.getdefaulttimeout() because it often gets reset, e.g. by
# socket.setblocking() and maybe other operations.
# http://stackoverflow.com/a/8465202/186123
socket.getdefaulttimeout = lambda: HTTP_TIMEOUT

# Add library modules directories to sys.path so they can be imported.
#
# I used to use symlinks and munge sys.modules, but both of those ended up in
# duplicate instances of modules, which caused problems. Background in
# https://github.com/snarfed/bridgy/issues/31
for path in (
  'google-api-python-client',
  'gdata-python-client/src',
  'httplib2_module/python2',
  'oauthlib_module',
  'python-dropbox',
  'requests_module',
  'requests-oauthlib',
  'python-tumblpy',
  'tweepy_module',
  ):
  path = os.path.join(os.path.dirname(__file__), path)
  if path not in sys.path:
    sys.path.append(path)

import python_dropbox
sys.modules['python_dropbox'] = python_dropbox


def read(filename):
  """Returns the contents of filename, or None if it doesn't exist."""
  if os.path.exists(filename):
    with open(filename) as f:
      return f.read().strip()

MOCKFACEBOOK = False

if DEBUG:
  FACEBOOK_APP_ID = read('facebook_app_id_local')
  FACEBOOK_APP_SECRET = read('facebook_app_secret_local')
  INSTAGRAM_CLIENT_ID = read('instagram_client_id_local')
  INSTAGRAM_CLIENT_SECRET = read('instagram_client_secret_local')
  WORDPRESS_CLIENT_ID = read('wordpress.com_client_id_local')
  WORDPRESS_CLIENT_SECRET = read('wordpress.com_client_secret_local')
  DISQUS_CLIENT_ID = read('disqus_client_id_local')
  DISQUS_CLIENT_SECRET = read('disqus_client_secret_local')
else:
  FACEBOOK_APP_ID = read('facebook_app_id')
  FACEBOOK_APP_SECRET = read('facebook_app_secret')
  INSTAGRAM_CLIENT_ID = read('instagram_client_id')
  INSTAGRAM_CLIENT_SECRET = read('instagram_client_secret')
  WORDPRESS_CLIENT_ID = read('wordpress.com_client_id')
  WORDPRESS_CLIENT_SECRET = read('wordpress.com_client_secret')
  DISQUS_CLIENT_ID = read('disqus_client_id')
  DISQUS_CLIENT_SECRET = read('disqus_client_secret')

DROPBOX_APP_KEY = read('dropbox_app_key')
DROPBOX_APP_SECRET = read('dropbox_app_secret')
FLICKR_APP_KEY = read('flickr_app_key')
FLICKR_APP_SECRET = read('flickr_app_secret')
GOOGLE_CLIENT_ID = read('google_client_id')
GOOGLE_CLIENT_SECRET = read('google_client_secret')
TUMBLR_APP_KEY = read('tumblr_app_key')
TUMBLR_APP_SECRET = read('tumblr_app_secret')
TWITTER_APP_KEY = read('twitter_app_key')
TWITTER_APP_SECRET = read('twitter_app_secret')
