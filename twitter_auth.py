"""Utility functions for handling Twitter OAuth.
"""

import appengine_config
import requests_oauthlib
import tweepy


def oauth1(token_key, token_secret):
  """Returns a requests_oauthlib.OAuth1 object.

  Args:
    token_key: string
    token_secret: string
  """
  return requests_oauthlib.OAuth1(
    client_key=appengine_config.TWITTER_APP_KEY,
    client_secret=appengine_config.TWITTER_APP_SECRET,
    resource_owner_key=token_key,
    resource_owner_secret=token_secret,
    )


def tweepy_auth(token_key, token_secret):
  """Returns a tweepy.OAuthHandler.
  """
  assert (appengine_config.TWITTER_APP_KEY and
          appengine_config.TWITTER_APP_SECRET), (
    "Please fill in the twitter_app_key and twitter_app_secret files in "
    "your app's root directory.")
  handler = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                             appengine_config.TWITTER_APP_SECRET)
  handler.set_access_token(token_key, token_secret)
  return handler

