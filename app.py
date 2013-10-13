#!/usr/bin/env python
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
    entity_key = self.request.get('entity_key')
    if entity_key:
      vars['entity'] = db.get(entity_key)

    self.response.out.write(template.render('templates/index.html', vars))


application = webapp2.WSGIApplication(
  [('/', FrontPageHandler)])


if __name__ == '__main__':
  main()
