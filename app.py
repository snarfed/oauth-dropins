#!/usr/bin/env python
"""Serves the HTML front page and discovery files.
"""

import appengine_config

from google.appengine.ext.webapp import template
import webapp2


class FrontPageHandler(webapp2.RequestHandler):
  """Renders and serves /, ie the front page.
  """
  def get(self):
    self.response.headers['Content-Type'] = 'text/html'

    vars = {}
    # add query params. use a list for params with multiple values.
    for key in self.request.params:
      values = self.request.params.getall(key)
      if len(values) == 1:
        values = values[0]
      vars[key] = values

    self.response.out.write(template.render('templates/index.html', vars))


application = webapp2.WSGIApplication(
  [('/', FrontPageHandler)])


if __name__ == '__main__':
  main()
