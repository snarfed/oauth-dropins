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

# default network timeout to 60s. the G+ and Instagram APIs use httplib2, which
# honors this.
import socket
socket.setdefaulttimeout(60)
# monkey-patch socket.getdefaulttimeout() because it often gets reset, e.g. by
# socket.setblocking() and maybe other operations.
# http://stackoverflow.com/a/8465202/186123
socket.getdefaulttimeout = lambda: 60

# Import library modules.
#
# To prevent duplicating modules under different names, we import here and set
# up sys.modules entries instead of munging sys.path or using other tricks.
# Background in https://github.com/snarfed/bridgy/issues/31
import apiclient; sys.modules['apiclient'] = apiclient
import atom; sys.modules['atom'] = atom
import gdata; sys.modules['gdata'] = gdata
import httplib2; sys.modules['httplib2'] = httplib2
import oauth2client; sys.modules['oauth2client'] = oauth2client
import oauthlib; sys.modules['oauthlib'] = oauthlib
import python_instagram; sys.modules['python_instagram'] = python_instagram
import requests; sys.modules['requests'] = requests
import requests_oauthlib; sys.modules['requests_oauthlib'] = requests_oauthlib
import tumblpy; sys.modules['tumblpy'] = tumblpy
import uritemplate; sys.modules['uritemplate'] = uritemplate
# tweepy imports from itself with e.g. 'from tweepy.models import ...',
# so temporarily munge sys.path to make that work.
sys.path.append(os.path.dirname(__file__))
try:
  import tweepy; sys.modules['tweepy'] = tweepy
finally:
  sys.path.pop()

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
else:
  FACEBOOK_APP_ID = read('facebook_app_id')
  FACEBOOK_APP_SECRET = read('facebook_app_secret')
  INSTAGRAM_CLIENT_ID = read('instagram_client_id')
  INSTAGRAM_CLIENT_SECRET = read('instagram_client_secret')
  WORDPRESS_CLIENT_ID = read('wordpress.com_client_id')
  WORDPRESS_CLIENT_SECRET = read('wordpress.com_client_secret')

DROPBOX_APP_KEY = read('dropbox_app_key')
DROPBOX_APP_SECRET = read('dropbox_app_secret')
GOOGLE_CLIENT_ID = read('google_client_id')
GOOGLE_CLIENT_SECRET = read('google_client_secret')
TUMBLR_APP_KEY = read('tumblr_app_key')
TUMBLR_APP_SECRET = read('tumblr_app_secret')
TWITTER_APP_KEY = read('twitter_app_key')
TWITTER_APP_SECRET = read('twitter_app_secret')
