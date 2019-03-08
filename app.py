"""Example oauth-dropins app. Serves the front page and discovery files.
"""

import appengine_config
import jinja2

from google.appengine.ext import ndb
import webapp2

from oauth_dropins.webutil import handlers

from oauth_dropins import (
  blogger_v2,
  disqus,
  dropbox,
  facebook,
  flickr,
  github,
  google_signin,
  indieauth,
  instagram,
  linkedin,
  medium,
  tumblr,
  twitter,
  wordpress_rest,
)


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


application = webapp2.WSGIApplication([
    ('/', FrontPageHandler),
    ('/blogger_v2/start', blogger_v2.StartHandler.to('/blogger_v2/oauth_callback')),
    ('/blogger_v2/oauth_callback', blogger_v2.CallbackHandler.to('/')),
    ('/disqus/start', disqus.StartHandler.to('/disqus/oauth_callback')),
    ('/disqus/oauth_callback', disqus.CallbackHandler.to('/')),
    ('/dropbox/start', dropbox.StartHandler.to('/dropbox/oauth_callback')),
    ('/dropbox/oauth_callback', dropbox.CallbackHandler.to('/')),
    ('/facebook/start', facebook.StartHandler.to('/facebook/oauth_callback')),
    ('/facebook/oauth_callback', facebook.CallbackHandler.to('/')),
    ('/flickr/start', flickr.StartHandler.to('/flickr/oauth_callback')),
    ('/flickr/oauth_callback', flickr.CallbackHandler.to('/')),
    ('/github/start', github.StartHandler.to('/github/oauth_callback')),
    ('/github/oauth_callback', github.CallbackHandler.to('/')),
    ('/google/start', google_signin.StartHandler.to('/google/oauth_callback')),
    ('/google/oauth_callback', google_signin.CallbackHandler.to('/')),
    ('/indieauth/start', indieauth.StartHandler.to('/indieauth/oauth_callback')),
    ('/indieauth/oauth_callback', indieauth.CallbackHandler.to('/')),
    ('/instagram/start', instagram.StartHandler.to('/instagram/oauth_callback')),
    ('/instagram/oauth_callback', instagram.CallbackHandler.to('/')),
    ('/linkedin/start', linkedin.StartHandler.to('/linkedin/oauth_callback')),
    ('/linkedin/oauth_callback', linkedin.CallbackHandler.to('/')),
    ('/medium/start', medium.StartHandler.to('/medium/oauth_callback')),
    ('/medium/oauth_callback', medium.CallbackHandler.to('/')),
    ('/tumblr/start', tumblr.StartHandler.to('/tumblr/oauth_callback')),
    ('/tumblr/oauth_callback', tumblr.CallbackHandler.to('/')),
    ('/twitter/start', twitter.StartHandler.to('/twitter/oauth_callback')),
    ('/twitter/oauth_callback', twitter.CallbackHandler.to('/')),
    ('/wordpress_rest/start', wordpress_rest.StartHandler.to(
        '/wordpress_rest/oauth_callback')),
    ('/wordpress_rest/oauth_callback', wordpress_rest.CallbackHandler.to('/')),
    ], debug=appengine_config.DEBUG)
