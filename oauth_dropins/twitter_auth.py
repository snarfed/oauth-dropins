"""Utility functions for generating Twitter OAuth headers and making API calls.

This is a separate module from twitter.py so that projects like granary can use
it without pulling in App Engine dependencies.

Supports Python 3. Should not depend on App Engine API or SDK packages.
"""
import urllib.request

import requests
import requests_oauthlib
import tweepy

from .webutil import util

TWITTER_APP_KEY = util.read('twitter_app_key')
TWITTER_APP_SECRET = util.read('twitter_app_secret')


def auth_header(url, token_key, token_secret, method='GET'):
  """Generates an Authorization header and returns it in a header dict.

  Args:
    url: string
    token_key: string
    token_secret: string
    method: string

  Returns:
    dict: single element with key 'Authorization'
  """
  oauth1 = requests_oauthlib.OAuth1(
    client_key=TWITTER_APP_KEY,
    client_secret=TWITTER_APP_SECRET,
    resource_owner_key=token_key,
    resource_owner_secret=token_secret,
  )
  req = requests.Request(method=method, url=url, auth=oauth1).prepare()
  return req.headers


def signed_urlopen(url, token_key, token_secret, headers=None, **kwargs):
  """Wraps urllib.request.urlopen() and adds an OAuth signature.
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
  return util.urlopen(urllib.request.Request(url, headers=headers, **kwargs))


def tweepy_auth(token_key, token_secret):
  """Returns a tweepy.OAuth.
  """
  assert TWITTER_APP_KEY and TWITTER_APP_SECRET, \
    "Please fill in the twitter_app_key and twitter_app_secret files in your app's root directory."
  view = tweepy.OAuth(TWITTER_APP_KEY, TWITTER_APP_SECRET)
  view.set_access_token(token_key, token_secret)
  return view
