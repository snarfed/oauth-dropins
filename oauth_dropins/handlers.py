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
import urllib

import webapp2
from webutil import handlers
from webutil import util


class BaseHandler(webapp2.RequestHandler):
  """Base request handler class. Provides the to() factory method.
  """
  DEFAULT_SCOPE = ''  # may be overridden by subclasses

  handle_exception = handlers.handle_exception
  to_path = None

  @classmethod
  def to(cls, path, scopes=None):
    class ToHandler(cls):
      to_path = path
      scope = cls.make_scope_str(scopes)
    return ToHandler

  @classmethod
  def make_scope_str(cls, extra, separator=','):
    """Returns an OAuth scopes query parameter value.

    Combines DEFAULT_SCOPE and extra.

    Args:
      extra: string, sequence of strings, or None
      separator: string (optional), the separator between multiple scopes.
        defaults to ','
    """
    if not extra:
      return cls.DEFAULT_SCOPE

    return (cls.DEFAULT_SCOPE + separator if cls.DEFAULT_SCOPE else '') + (
      extra if isinstance(extra, basestring) else separator.join(extra))

  def to_url(self, state=None):
    """Returns a fully qualified callback URL based on to_path.

    Includes scheme, host, and optional state.
    """
    url = self.request.host_url + self.to_path
    if state:
      # unquote first or state will be double-quoted
      state = urllib.unquote_plus(state)
      url = util.add_query_params(url, [('state', state)])
    return url

  def request_url_with_state(self):
    """Returns the current request URL, with the state query param if provided.
    """
    state = self.request.get('state')
    if state:
      return util.add_query_params(self.request.path_url, [('state', state)])
    else:
      return self.request.path_url


class StartHandler(BaseHandler):
  """Base class for starting an OAuth flow.

  Users should use the to() class method when using this request handler in a
  WSGI application. See the file docstring for details.

  If the 'state' query parameter is provided in the request data, it will be
  returned to the client in the OAuth callback handler. If the 'scope' query
  parameter is provided, it will be added to the existing OAuth scopes.

  Alternatively, clients may call redirect_url() and HTTP 302 redirect to it
  manually, which will start the same OAuth flow.
  """

  def __init__(self, *args, **kwargs):
    assert self.to_path, 'No `to` URL. Did you forget to use the to() class method in your request handler mapping?'
    super(StartHandler, self).__init__(*args, **kwargs)

  def get(self):
    self.post()

  def post(self):
    scopes = self.request.params.getall('scope')
    if scopes:
      self.scope += (',' if self.scope else '') + ','.join(scopes)

    url = self.redirect_url(state=self.request.get('state'))
    logging.info('Starting OAuth flow: redirecting to %s', url)
    self.redirect(url)

  def redirect_url(self, state=None):
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
      auth_entity: a site-specific subclass of models.BaseAuth, or None if the
        user declined the site's OAuth authorization request.
      state: the string passed to StartHandler.redirect_url()
    """
    assert self.to_path, 'No `to` URL. Did you forget to use the to() class method in your request handler mapping?'

    if auth_entity is None:
      params = [('declined', True)]
    else:
      params = [('auth_entity', auth_entity.key.urlsafe()), ('state', state)]
      token = auth_entity.access_token()
      if isinstance(token, basestring):
        params.append(('access_token', token))
      elif token:
        params += [('access_token_key', token[0]),
                   ('access_token_secret', token[1])]

    url = util.add_query_params(self.to_path, params)
    logging.info('Finishing OAuth flow: redirecting to %s', url)
    self.redirect(url)
