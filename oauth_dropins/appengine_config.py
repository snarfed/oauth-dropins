"""App Engine settings.

Reads app keys and secrets from local files into constants.
"""
from __future__ import absolute_import

import os

from .webutil.appengine_config import *

# quiet down oauth1 log messages
import logging
logging.getLogger('oauthlib').setLevel(logging.INFO)
logging.getLogger('requests_oauthlib').setLevel(logging.INFO)

# default timeout. the G+ and Instagram APIs use httplib2, which honors this.
import socket
socket.setdefaulttimeout(HTTP_TIMEOUT)
# monkey-patch socket.getdefaulttimeout() because it often gets reset, e.g. by
# socket.setblocking() and maybe other operations.
# http://stackoverflow.com/a/8465202/186123
socket.getdefaulttimeout = lambda: HTTP_TIMEOUT

# Twitter returns HTTP 429 for rate limiting, which webob doesn't know. Tell it.
try:
  import webob
  try:
    webob.util.status_reasons[429] = 'Twitter rate limited'  # webob <= 0.9
  except AttributeError:
    webob.status_reasons[429] = 'Twitter rate limited'  # webob >= 1.1.1
except ImportError:
  webob = None

def read(filename):
  """Returns the contents of filename, or None if it doesn't exist."""
  if os.path.exists(filename):
    with open(filename) as f:
      return f.read().strip()

if DEBUG:
  # read these from env vars if available. used in CircleCI:
  # https://circleci.com/gh/snarfed/bridgy/edit#env-vars
  FACEBOOK_APP_ID = (os.getenv('FACEBOOK_APP_ID') or
                     read('facebook_app_id_local'))
  FACEBOOK_APP_SECRET = (os.getenv('FACEBOOK_APP_SECRET') or
                         read('facebook_app_secret_local'))
  GITHUB_CLIENT_ID = read('github_client_id_local')
  GITHUB_CLIENT_SECRET = read('github_client_secret_local')
  INSTAGRAM_CLIENT_ID = read('instagram_client_id_local')
  INSTAGRAM_CLIENT_SECRET = read('instagram_client_secret_local')
  WORDPRESS_CLIENT_ID = read('wordpress.com_client_id_local')
  WORDPRESS_CLIENT_SECRET = read('wordpress.com_client_secret_local')
  DISQUS_CLIENT_ID = read('disqus_client_id_local')
  DISQUS_CLIENT_SECRET = read('disqus_client_secret_local')
else:
  FACEBOOK_APP_ID = (os.getenv('FACEBOOK_APP_ID') or
                     read('facebook_app_id'))
  FACEBOOK_APP_SECRET = (os.getenv('FACEBOOK_APP_SECRET') or
                         read('facebook_app_secret'))
  GITHUB_CLIENT_ID = read('github_client_id')
  GITHUB_CLIENT_SECRET = read('github_client_secret')
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
INDIEAUTH_CLIENT_ID = read('indieauth_client_id')
INSTAGRAM_SESSIONID_COOKIE = (os.getenv('INSTAGRAM_SESSIONID_COOKIE') or
                              read('instagram_sessionid_cookie'))
MEDIUM_CLIENT_ID = read('medium_client_id')
MEDIUM_CLIENT_SECRET = read('medium_client_secret')
TUMBLR_APP_KEY = read('tumblr_app_key')
TUMBLR_APP_SECRET = read('tumblr_app_secret')
TWITTER_APP_KEY = read('twitter_app_key')
TWITTER_APP_SECRET = read('twitter_app_secret')
