"""Base OAuth flow views. Clients should use the individual site modules.

Example usage:

app = Flask()

app.add_url_rule('/start',
                 view_func=twitter.Start.as_view('start', '/callback'),
                 methods=['POST'])
app.add_url_rule('/callback',
                 view_func=twitter.Callback.as_view('callback', '/after'))
"""
import logging
import urllib.parse

import flask
from flask import request
from flask.views import View

from .webutil import util

logger = logging.getLogger(__name__)


class BaseView(View):
  """Base view class. Provides the to() factory method.

  Attributes (some may be overridden by subclasses):
    DEFAULT_SCOPE: string, default OAuth scope(s) to request
    SCOPE_SEPARATOR: string, used to separate multiple scopes
    LABEL: string, human-readable label, eg 'Blogger'
    NAME: string module name; usually same as `__name__.split('.')[-1]`
    to_path: the base redirect URL path for the OAuth callback
    scope: OAuth scopes string, comma-separated
  """
  DEFAULT_SCOPE = ''
  SCOPE_SEPARATOR = ','
  LABEL = None
  NAME = None

  to_path = None
  scope = None

  def __init__(self, to_path, scopes=None):
    super().__init__()
    assert to_path
    self.to_path = to_path
    self.scope = self.make_scope_str(scopes)

  @classmethod
  def make_scope_str(cls, extra):
    """Returns an OAuth scopes query parameter value.

    Combines DEFAULT_SCOPE and extra.

    Args:
      extra: string, sequence of strings, or None
    """
    if not extra:
      return cls.DEFAULT_SCOPE

    if not isinstance(extra, str):
      extra = cls.SCOPE_SEPARATOR.join(extra)

    return cls.SCOPE_SEPARATOR.join(util.trim_nulls((cls.DEFAULT_SCOPE, extra)))

  def to_url(self, state=None):
    """Returns a fully qualified callback URL based on to_path.

    Includes scheme, host, and optional state.
    """
    url = urllib.parse.urljoin(request.host_url, self.to_path)
    if state:
      # unquote first or state will be double-quoted
      state = urllib.parse.unquote_plus(state)
      url = util.add_query_params(url, [('state', state)])
    return url

  def request_url_with_state(self):
    """Returns the current request URL, with the state query param if provided.
    """
    state = request.values.get('state')
    if state:
      return util.add_query_params(request.base_url, [('state', state)])
    else:
      return request.base_url


class Start(BaseView):
  """Base class for starting an OAuth flow.

  Users should use the to() class method when using this view in a WSGI
  application. See the file docstring for details.

  If the 'state' query parameter is provided in the request data, it will be
  returned to the client in the OAuth callback view. If the 'scope' query
  parameter is provided, it will be added to the existing OAuth scopes.

  Alternatively, clients may call redirect_url() and HTTP 302 redirect to it
  manually, which will start the same OAuth flow.
  """

  def dispatch_request(self):
    scopes = set(request.values.getlist('scope'))
    if self.scope:
      scopes.add(self.scope)
    self.scope = self.SCOPE_SEPARATOR.join(util.trim_nulls(scopes))

    # str() is since WSGI middleware chokes on unicode redirect URLs :/ eg:
    # InvalidResponseError: header values must be str, got 'unicode' (u'...') for 'Location'
    # https://console.cloud.google.com/errors/CPafw-Gq18CrnwE
    url = str(self.redirect_url(state=request.values.get('state')))

    logger.info(f'Starting OAuth flow: redirecting to {url}')
    return flask.redirect(url)

  def redirect_url(self, state=None):
    """Returns the local URL for the OAuth service to redirect back to.

    oauth-dropin subclasses must implement this.

    Args:
      state: string, user-provided value to be returned as a query parameter in
        the return redirect
    """
    raise NotImplementedError()

  @classmethod
  def button_html(cls, to_path, form_classes='', form_method='post',
                  form_extra='', image_prefix='', image_file=None,
                  input_style='', scopes='', outer_classes=''):
    """Returns an HTML string with a login form and button for this site.

    Args:
      to_path: string, path or URL for the form to POST to
      form_classes: string, optional, HTML classes to add to the <form>
      form_classes: string, optional, HTML classes to add to the outer <div>
      form_method: string, optional, form action ie HTTP method, eg 'get';
        defaults to 'post'
      form_extra: string, optional, extra HTML to insert inside the <form>
        before the button
      scopes: string, optional, OAuth scopes to override site's default(s)
      image_prefix: string, optional, prefix to add to the beginning of image
        URL path, eg '/oauth_dropins/'
      image_file: string, optional, image filename. defaults to [cls.NAME].png
      input_style: string, optional, inline style to apply to the button <input>

    Returns: string
    """
    if image_file is None:
      image_file = f'{cls.NAME}_2x.png'
    vars = locals()
    vars.update({
      'label': cls.LABEL,
      'image': urllib.parse.urljoin(image_prefix, image_file),
    })
    html = f"""<form method="{vars['form_method']}" action="{vars['to_path']}" class="{vars['form_classes']}">
  <nobr>
    {vars['form_extra']}
    <input type="image" height="50" title="{vars['label']}" class="shadow"
           src="{vars['image']}" style="{vars['input_style']}" />
    <input name="scope" type="hidden" value="{vars['scopes']}">
  </nobr>
</form>
"""
    if outer_classes:
      html = f'<div class="{outer_classes}">{html}</div>'
    return html


class Callback(BaseView):
  """Base OAuth callback view.

  Users can use the to() class method when using this view in a WSGI
  application to make it redirect to a given URL path on completion. See the
  file docstring for details.

  Alternatively, you can subclass it and implement finish(), which will be
  called in the OAuth callback request directly, after the user has been
  authenticated.

  The auth entity and optional state parameter provided to Start will be
  passed to finish() or as query parameters to the redirect URL.
  """

  def finish(self, auth_entity, state=None):
    """Called when the OAuth flow is complete. Clients may override.

    Args:
      auth_entity: a site-specific subclass of models.BaseAuth, or None if the
        user declined the site's OAuth authorization request.
      state: the string passed to Start.redirect_url()

    Returns: :class:`werkzeug.wrappers.Response`
    """
    if auth_entity is None:
      params = [('declined', True)]
    else:
      params = [('auth_entity', auth_entity.key.urlsafe().decode()),
                ('state', state)]
      try:
        token = auth_entity.access_token()
        if isinstance(token, str):
          params.append(('access_token', token))
        elif token:
          params += [('access_token_key', token[0]),
                     ('access_token_secret', token[1])]
      except NotImplementedError:
        logger.info('access_token() not implemented')
      try:
        token = auth_entity.refresh_token
        params.append(('refresh_token', token))
      except AttributeError:
        logger.info('refresh_token not included')

    url = util.add_query_params(self.to_path, params)
    logger.info(f'Finishing OAuth flow: redirecting to {url}')
    return flask.redirect(url)
