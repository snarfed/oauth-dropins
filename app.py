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

SITES = {}  # maps module name to module
for name in (
    'blogger_v2',
    'disqus',
    'dropbox',
    'facebook',
    'flickr',
    'github',
    'google_signin',
    'indieauth',
    'instagram',
    'linkedin',
    'mastodon',
    'medium',
    'tumblr',
    'twitter',
    'wordpress_rest',
  ):
  SITES[name] = importlib.import_module('oauth_dropins.%s' % name)


def handle_discovery_errors(handler, e, debug):
  """A webapp2 exception handler that handles URL discovery errors.

  Used to catch Mastodon and IndieAuth connection failures, etc.
  """
  if isinstance(e, (ValueError, requests.RequestException, exc.HTTPException)):
    logging.warning('', exc_info=True)
    return handler.redirect('/?' + urllib.urlencode({'error': str(e)}))

  raise


class FrontPageHandler(handlers.TemplateHandler):
  """Renders and serves /, ie the front page.
  """
  def template_file(self):
    return 'templates/index.html'

  def template_vars(self, *args, **kwargs):
    vars = dict(self.request.params)
    key = vars.get('auth_entity')
    if key:
      vars['entity'] = ndb.Key(urlsafe=key).get()

    vars.update({
      site + '_html': module.StartHandler.button_html('/%s/start' % site)
      for site, module in SITES.items()})
    return vars


class IndieAuthStart(indieauth.StartHandler):
  handle_exception = handle_discovery_errors

class MastodonStart(mastodon.StartHandler):
  handle_exception = handle_discovery_errors


routes = []
for site, module in SITES.items():
  starter = (IndieAuthStart if site == 'indieauth'
             else MastodonStart if site == 'mastodon'
             else module.StartHandler)
  routes.extend((
    ('/%s/start' % site, starter.to('/%s/oauth_callback' % site)),
    ('/%s/oauth_callback' % site, module.CallbackHandler.to('/')),
  ))

application = webapp2.WSGIApplication([
    ('/', FrontPageHandler),
  ] + routes, debug=appengine_config.DEBUG)
