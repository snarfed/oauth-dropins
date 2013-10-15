"""Serves the HTML front page and discovery files.
"""

import appengine_config

# import all the sites because we load their model classes.
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


class FacebookStartHandler(facebook.StartHandler):
  callback_path = '/facebook/oauth_callback'

class FacebookCallbackHandler(facebook.CallbackHandler):
  redirect_url = '/'


class TwitterStartHandler(twitter.StartHandler):
  callback_path = '/twitter/oauth_callback'

class TwitterCallbackHandler(twitter.CallbackHandler):
  redirect_url = '/'


application = webapp2.WSGIApplication([
    ('/', FrontPageHandler),
    ('/facebook/start', FacebookStartHandler),
    ('/facebook/oauth_callback', FacebookCallbackHandler),
    ('/twitter/start', TwitterStartHandler),
    ('/twitter/oauth_callback', TwitterCallbackHandler),
    ], debug=appengine_config.DEBUG)


if __name__ == '__main__':
  main()
