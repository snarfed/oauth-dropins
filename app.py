"""Example oauth-dropins app. Serves the front page and discovery files.
"""
from collections import defaultdict
import importlib
import logging
import urllib

import appengine_config
from google.appengine.ext import ndb
import jinja2
import requests
import webapp2
from webob import exc
from oauth_dropins.webutil import handlers

from oauth_dropins import indieauth, mastodon


def handle_discovery_errors(handler, e, debug):
  """A webapp2 exception handler that handles URL discovery errors.

  Used to catch Mastodon and IndieAuth connection failures, etc.
  """
  if isinstance(e, (ValueError, requests.RequestException, exc.HTTPException)):
    logging.warning('', exc_info=True)
    return handler.redirect('/?' + urllib.urlencode({'error': str(e)}))

  raise


class FrontPageHandler(handlers.ModernHandler):
  """Renders and serves /, ie the front page.
  """
  def get(self):
    self.response.headers['Content-Type'] = 'text/html'

    vars = dict(self.request.params)
    key = vars.get('auth_entity')
    if key:
      vars['entity'] = ndb.Key(urlsafe=key).get()

    env = jinja2.Environment(loader=jinja2.FileSystemLoader(('.')), autoescape=True)
    self.response.out.write(env.get_template('templates/index.html').render(vars))


class IndieAuthStart(indieauth.StartHandler):
  handle_exception = handle_discovery_errors

class MastodonStart(mastodon.StartHandler):
  handle_exception = handle_discovery_errors


routes = [
    ('/indieauth/start', IndieAuthStart.to('/indieauth/oauth_callback')),
    ('/indieauth/oauth_callback', indieauth.CallbackHandler.to('/')),
    ('/mastodon/start', MastodonStart.to('/mastodon/oauth_callback')),
    ('/mastodon/oauth_callback', mastodon.CallbackHandler.to('/')),
]

for name in (
    'blogger_v2',
    'disqus',
    'dropbox',
    'facebook',
    'flickr',
    'github',
    'google_signin',
    'instagram',
    'linkedin',
    'medium',
    'tumblr',
    'twitter',
    'wordpress_rest',
  ):
  module = importlib.import_module('oauth_dropins.%s' % name)
  routes.extend((
    ('/%s/start' % name, module.StartHandler.to('/%s/oauth_callback' % name)),
    ('/%s/oauth_callback' % name, module.CallbackHandler.to('/')),
  ))

application = webapp2.WSGIApplication([
    ('/', FrontPageHandler),
  ] + routes, debug=appengine_config.DEBUG)
