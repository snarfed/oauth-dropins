"""Serves the HTML front page and discovery files.
"""

import appengine_config

import blogger_v2
import dropbox
import facebook
import googleplus
import instagram
import tumblr
import twitter
import wordpress_rest

from google.appengine.ext import db
from google.appengine.ext.webapp import template
import webapp2


class FrontPageHandler(webapp2.RequestHandler):
  """Renders and serves /, ie the front page.
  """
  def get(self):
    self.response.headers['Content-Type'] = 'text/html'

    vars = {}
    key = self.request.get('auth_entity')
    if key:
      vars['entity'] = db.get(key)

    self.response.out.write(template.render('templates/index.html', vars))


application = webapp2.WSGIApplication([
    ('/', FrontPageHandler),
    ('/dropbox/start', dropbox.StartHandler.to('/dropbox/oauth_callback')),
    ('/dropbox/oauth_callback', dropbox.CallbackHandler.to('/')),
    ('/facebook/start', facebook.StartHandler.to('/facebook/oauth_callback')),
    ('/facebook/oauth_callback', facebook.CallbackHandler.to('/')),
    ('/instagram/start', instagram.StartHandler.to('/instagram/oauth_callback')),
    ('/instagram/oauth_callback', instagram.CallbackHandler.to('/')),
    ('/twitter/start', twitter.StartHandler.to('/twitter/oauth_callback')),
    ('/twitter/oauth_callback', twitter.CallbackHandler.to('/')),
    ], debug=appengine_config.DEBUG)


if __name__ == '__main__':
  main()
