"""Flask app config.

http://flask.pocoo.org/docs/2.0/config
"""
from oauth_dropins.webutil import appengine_info, util

if appengine_info.DEBUG:
  ENV = 'development'
  CACHE_TYPE = 'NullCache'
  SECRET_KEY = 'sooper seekret'
else:
  ENV = 'production'
  CACHE_TYPE = 'SimpleCache'
  SECRET_KEY = util.read('flask_secret_key')


# # turn on verbose HTTP request logging
# # https://requests.readthedocs.io/en/latest/api/#:~:text=be%20handled%20by-,configuring%20logging
# from http.client import HTTPConnection
# HTTPConnection.debuglevel = 1

# import logging
# logging.getLogger().setLevel(logging.DEBUG)
# requests_log = logging.getLogger('urllib3')
# requests_log.setLevel(logging.DEBUG)
# requests_log.propagate = True
