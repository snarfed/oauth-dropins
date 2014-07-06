"""Utility functions for generating Twitter OAuth headers and making API calls.
"""

import logging
import urllib2
import urlparse

import appengine_config
import tweepy


def auth_header(url, token_key, token_secret, method='GET'):
  """Generates an Authorization header and returns it in a header dict.

  Args:
    url: string
    token_key: string
    token_secret: string
    method: string

  Returns: single element dict with key 'Authorization'
  """
  parsed = urlparse.urlparse(url)
  url_without_query = urlparse.urlunparse(list(parsed[0:4]) + ['', ''])
  header = {}
  auth = tweepy_auth(token_key, token_secret)
  auth.apply_auth(url_without_query, method, header,
                  dict(urlparse.parse_qsl(parsed.query)))
  logging.debug(
    'Generated Authorization header from access token key %s... and secret %s...',
    token_key[:4], token_secret[:4])
  return header


def signed_urlopen(url, token_key, token_secret, headers=None, **kwargs):
  """Wraps urllib2.urlopen() and adds an OAuth signature.
  """
  if headers is None:
    headers = {}

  # if this is a post, move the body params into the URL. Tweepy's OAuth
  # signing doesn't work if they're in the body; Twitter returns a 401.
  data = kwargs.get('data')
  if data:
    method = 'POST'
    url += ('&' if '?' in url else '?') + data
    kwargs['data'] = ''
  else:
    method = 'GET'

  headers.update(auth_header(url, token_key, token_secret, method=method))
  timeout = kwargs.pop('timeout', appengine_config.HTTP_TIMEOUT)
  logging.debug('Fetching %s', url)
  return urllib2.urlopen(urllib2.Request(url, headers=headers, **kwargs),
                         timeout=timeout)


def tweepy_auth(token_key, token_secret):
  """Returns a tweepy.OAuthHandler.
  """
  assert (appengine_config.TWITTER_APP_KEY and
          appengine_config.TWITTER_APP_SECRET), (
    "Please fill in the twitter_app_key and twitter_app_secret files in "
    "your app's root directory.")
  auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                             appengine_config.TWITTER_APP_SECRET)
  # make sure token key and secret aren't unicode because python's hmac
  # module (used by tweepy/oauth.py) expects strings.
  # http://stackoverflow.com/questions/11396789
  # fixed in https://github.com/tweepy/tweepy/commit/5a22bf73ccf7fae3d2b10314ce7f8eef067fee7a
  auth.set_access_token(str(token_key), str(token_secret))
  return auth

