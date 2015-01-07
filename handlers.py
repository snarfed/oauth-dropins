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

import apiclient
from oauth2client.client import AccessTokenRefreshError
import requests
import urllib2
import webapp2
from webob import exc
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
  def make_scope_str(cls, extra):
    """Returns an OAuth scopes query parameter value.

    Combines DEFAULT_SCOPE and extra.

    Args:
      extra: string, sequence of strings, or None
    """
    if extra is None:
      return cls.DEFAULT_SCOPE
    elif isinstance(extra, basestring):
      return cls.DEFAULT_SCOPE + ',' + extra
    else:
      return cls.DEFAULT_SCOPE + ','.join(extra)

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
      self.scope += ',' + ','.join(scopes)

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
      else:
        params += [('access_token_key', token[0]),
                   ('access_token_secret', token[1])]

    url = util.add_query_params(self.to_path, params)
    logging.info('Finishing OAuth flow: redirecting to %s', url)
    self.redirect(url)


def interpret_http_exception(exception):
  """Extracts the status code and response from different HTTP exception types.

  Args:
    exc: one of:
      apiclient.errors.HttpError
      exc.WSGIHTTPException
      oauth2client.client.AccessTokenRefreshError
      requests.HTTPError
      urllib2.HTTPError
      urllib2.URLError

  Returns: (string status code or None, string response body or None)
  """
  e = exception
  code = body = None

  if isinstance(e, exc.WSGIHTTPException):
    code = e.code
    body = e.plain_body({})

  elif isinstance(e, urllib2.HTTPError):
    code = e.code
    try:
      body = e.read()
      e.fp.seek(0)  # preserve the body so it can be read again
    except AttributeError:
      body = e.reason

  elif isinstance(e, urllib2.URLError):
    body = e.reason

  elif isinstance(e, requests.HTTPError):
    code = e.response.status_code
    body = e.response.text

  elif isinstance(e, apiclient.errors.HttpError):
    code = e.resp.status
    body = e.content

  elif isinstance(e, AccessTokenRefreshError) and str(e) == 'invalid_grant':
    code = '401'

  # instagram-specific error_types that should disable the source.
  if body and ('OAuthAccessTokenException' in body            # revoked access
               or 'APIRequiresAuthenticationError' in body):  # account deleted
    code = '401'

  if code:
    code = str(code)
  if code or body:
    logging.warning('Error %s, response body: %s', code, body)

  return code, body
