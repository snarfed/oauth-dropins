"""Based flow request handlers. Clients should use the site-specific subclasses.
"""

import logging

import webapp2
from webutil import handlers
from webutil import util

class StartHandler(webapp2.RequestHandler):
  """Base class for starting an OAuth flow.

  Clients may use this as the request handler class directly. It handles GET and
  POST requests, and if the 'state' query parameter is provided in the request
  data, it will be returned to the client in the OAuth callback handler.

  Alternatively, clients may call redirect_url() and HTTP 302 redirect to it
  manually, which will start the same OAuth flow.

  Clients *must* set the callback_path attribute. It should start with a /.
  """
  handle_exception = handlers.handle_exception
  callback_path = None

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


class CallbackHandler(webapp2.RequestHandler):
  """Base OAuth callback request handler.

  Clients may subclass this and implement finish(), which is called after the
  OAuth flow is done. Alternatively, they may set the redirect_url attr, and
  users will be redirected there.

  The auth entity and optional state parameter provided to StartHandler will be
  passed to finish() or as query parameters to the redirect URL.
  """
  handle_exception = handlers.handle_exception
  redirect_url = None

  def finish(self, auth_entity, state=None):
    """Called when the OAuth flow is complete. Clients may override.

    Args:
      auth_entity: a site-specific subclass of models.BaseAuth
      state: the string passed to StartHandler.redirect_url()
    """
    assert self.redirect_url, 'You must implement finish() or set redirect_url'
    params = [('auth_entity', auth_entity.key()), ('state', state)]
    url = util.add_query_params(self.redirect_url, params)
    logging.info('Finishing OAuth flow: redirecting to %s', url)
    self.redirect(url)
