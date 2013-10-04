"""Twitter OAuth drop-in.
"""

import logging
import urllib
from webob import exc

import appengine_config
import tweepy

from google.appengine.ext import db
import webapp2

OAUTH_CALLBACK = 'http://%s/twitter/oauth_callback' % appengine_config.HOST


class TwitterOAuthToken(db.Model):
  """Datastore model class for an OAuth token. The key name is the token key.
  """
  token_secret = db.StringProperty(required=True)


class StartHandler(webapp2.RequestHandler):
  """Starts three-legged OAuth with Twitter.

  Fetches an OAuth request token, then redirects to Twitter's auth page to
  request an access token.
  """
  def post(self):
    try:
      auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                                 appengine_config.TWITTER_APP_SECRET,
                                 OAUTH_CALLBACK)
      auth_url = auth.get_authorization_url()
    except tweepy.TweepError, e:
      msg = 'Could not create Twitter OAuth request token: '
      logging.exception(msg)
      raise exc.HTTPInternalServerError(msg + `e`)

    # store the request token for later use in the callback handler
    TwitterOAuthToken(key_name=auth.request_token.key,
                      token_secret=auth.request_token.secret).put()
    logging.info('Generated request token, redirecting to Twitter: %s', auth_url)
    self.redirect(auth_url)


class CallbackHandler(webapp2.RequestHandler):
  """The OAuth callback. Fetches an access token and redirects to the front page.
  """

  def get(self):
    oauth_token = self.request.get('oauth_token', None)
    oauth_verifier = self.request.get('oauth_verifier', None)
    if oauth_token is None:
      raise exc.HTTPBadRequest('Missing required query parameter oauth_token.')

    # Lookup the request token
    request_token = TwitterOAuthToken.get_by_key_name(oauth_token)
    if request_token is None:
      raise exc.HTTPBadRequest('Invalid oauth_token: %s' % oauth_token)

    # Rebuild the auth handler
    auth = tweepy.OAuthHandler(appengine_config.TWITTER_APP_KEY,
                               appengine_config.TWITTER_APP_SECRET)
    auth.set_request_token(request_token.key().name(), request_token.token_secret)

    # Fetch the access token
    try:
      access_token = auth.get_access_token(oauth_verifier)
    except tweepy.TweepError, e:
      msg = 'Twitter OAuth error, could not get access token: '
      logging.exception(msg)
      raise exc.HTTPInternalServerError(msg + `e`)

    self.redirect('/?%s' % urllib.urlencode(
        {'twitter_token_key': access_token.key,
         'twitter_token_secret': access_token.secret,
         }))


application = webapp2.WSGIApplication([
    ('/twitter/start', StartHandler),
    ('/twitter/oauth_callback', CallbackHandler),
    ], debug=appengine_config.DEBUG)
