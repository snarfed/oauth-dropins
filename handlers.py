"""Based flow request handlers. Clients should use the individual site modules.

Example usage:

application = webapp2.WSGIApplication([
  ('/oauth_start', facebook.StartHandler.to('/oauth_callback')),
  ('/oauth_callback', facebook.CallbackHandler.to('/done')),
  ('/done', AuthenticatedHandler),
  ...
  ]
"""

import logging

import webapp2
from webutil import handlers
from webutil import util


class BaseHandler(webapp2.RequestHandler):
  """Base request handler class. Provides the to() factory method.
  """
  handle_exception = handlers.handle_exception
  to_path = None

  @classmethod
  def to(cls, path):
    class ToHandler(cls):
      to_path = path
    return ToHandler


class StartHandler(BaseHandler):
  """Base class for starting an OAuth flow.

  Users should use the to() class method when using this request handler in a
  WSGI application. See the file docstring for details.

  If the 'state' query parameter is provided in the request data, it will be
  returned to the client in the OAuth callback handler.

  Alternatively, clients may call redirect_url() and HTTP 302 redirect to it
  manually, which will start the same OAuth flow.
  """

  def __init__(self, *args, **kwargs):
    assert self.to_path, 'No `to` URL. Did you forget to use the to() class method in your request handler mapping?'
    super(StartHandler, self).__init__(*args, **kwargs)

  def get(self):
    self.post()

  def post(self):
    url = self.redirect_url(state=self.request.get('state'))
    logging.info('Starting OAuth flow: redirecting to %s', url)
    self.redirect(url)

  def redirect_url(self, state=''):
    """oauth-dropin subclasses must implement this.
    """
    raise NotImplementedError()


class CallbackHandler(BaseHandler):
  """Base OAuth callback request handler.

  Users can use the to() class method when using this request handler in a WSGI
  application to make it redirect to a given URL path on completion. See the
  file docstring for details.

  Alternatively, you can subclass it and implement finish(), which will be
  called in the OAuth callback request directly, after the user has been
  authenticated.

  The auth entity and optional state parameter provided to StartHandler will be
  passed to finish() or as query parameters to the redirect URL.
  """

  def finish(self, auth_entity, state=None):
    """Called when the OAuth flow is complete. Clients may override.

    Args:
      auth_entity: a site-specific subclass of models.BaseAuth
      state: the string passed to StartHandler.redirect_url()
    """
    assert self.to_path, 'No `to` URL. Did you forget to use the to() class method in your request handler mapping?'
    params = [('auth_entity', auth_entity.key()), ('state', state)]
    url = util.add_query_params(self.to_path, params)
    logging.info('Finishing OAuth flow: redirecting to %s', url)
    self.redirect(url)
