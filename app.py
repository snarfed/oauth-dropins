"""Example oauth-dropins app. Serves the front page and discovery files.
"""
import importlib

import appengine_config
import jinja2

from google.appengine.ext import ndb
import webapp2

from oauth_dropins.webutil import handlers


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


routes = []
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
  module = importlib.import_module('oauth_dropins.%s' % name)
  routes.extend((
    ('/%s/start' % name, module.StartHandler.to('/%s/oauth_callback' % name)),
    ('/%s/oauth_callback' % name, module.CallbackHandler.to('/')),
  ))

application = webapp2.WSGIApplication([
    ('/', FrontPageHandler),
  ] + routes, debug=appengine_config.DEBUG)
