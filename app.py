"""Example oauth-dropins app. Serves the front page and discovery files.
"""
import importlib
import logging
from urllib.parse import urlencode, urlparse

from flask import Flask, render_template, request
import flask
import flask_gae_static
from google.cloud import ndb
from oauth_dropins.webutil import flask_util, util
import requests
from werkzeug.exceptions import HTTPException

from oauth_dropins import bluesky
from oauth_dropins.views import get_logins, logout
from oauth_dropins.webutil import appengine_info, appengine_config

logger = logging.getLogger(__name__)

CACHE_CONTROL = {'Cache-Control': 'public, max-age=3600'}  # 1 hour

app = Flask(__name__, static_folder=None)
app.json.compact = False
app.config.from_pyfile('config.py')
app.wsgi_app = flask_util.ndb_context_middleware(
    app.wsgi_app, client=appengine_config.ndb_client)
if appengine_info.DEBUG or appengine_info.LOCAL_SERVER:
  flask_gae_static.init_app(app)

logging.getLogger('requests_oauthlib').setLevel(logging.DEBUG)

util.set_user_agent('oauth-dropins (https://oauth-dropins.appspot.com/)')


SITES = {name: importlib.import_module(f'oauth_dropins.{name}') for name in (
    'bluesky',
    'disqus',
    'dropbox',
    'facebook',
    'flickr',
    'github',
    'google_signin',
    'indieauth',
    'instagram',
    'linkedin',
    'mastodon',
    'meetup',
    'pixelfed',
    'reddit',
    'threads',
    'tumblr',
    'twitter',
    'wordpress_rest',
  )}
from oauth_dropins import google_signin
google_signin.Start.INCLUDE_GRANTED_SCOPES = False


class BlueskyStart(bluesky.OAuthStart):
  CLIENT_METADATA = bluesky._APP_CLIENT_METADATA

class BlueskyCallback(bluesky.OAuthCallback):
  CLIENT_METADATA = bluesky._APP_CLIENT_METADATA


for site, module in SITES.items():
  start = f'/{site}/start'
  callback = f'/{site}/oauth_callback'

  if site == 'bluesky':
    start_cls = BlueskyStart
    callback_cls = BlueskyCallback
  else:
    start_cls = module.Start
    callback_cls = module.Callback

  app.add_url_rule(start, view_func=start_cls.as_view(start, callback),
                   methods=['POST'])
  app.add_url_rule(callback, view_func=callback_cls.as_view(callback, '/'))


@app.errorhandler(Exception)
def handle_discovery_errors(e):
  """A Flask exception handler that handles URL discovery errors.

  Used to catch Mastodon and IndieAuth connection failures, etc.
  """
  if isinstance(e, HTTPException):
    return e

  if isinstance(e, (ValueError, requests.RequestException)):
    logger.warning('', exc_info=True)
    return flask.redirect('/?' + urlencode({'error': str(e)}))

  return flask_util.handle_exception(e)


@app.route('/')
def home_page():
  """Renders and serves the home page."""
  vars = {
    **dict(request.args),
    'get_logins': get_logins,
    'logout': logout,
    'request': request,
    'util': util,
  }
  vars.update({
    site + '_html': module.Start.button_html(
      '/%s/start' % site, image_prefix='/static/',
      outer_classes='col-md-3 col-sm-4 col-xs-6')
    for site, module in SITES.items()
  })

  if key := request.args.get('auth_entity'):
    vars['entity'] = ndb.Key(urlsafe=key).get()

  return render_template('index.html', **vars)


@app.get(urlparse(bluesky._APP_CLIENT_METADATA['client_id']).path)
@flask_util.headers(CACHE_CONTROL)
def bluesky_oauth_client_metadata():
  """https://docs.bsky.app/docs/advanced-guides/oauth-client#client-and-server-metadata"""
  return bluesky._APP_CLIENT_METADATA
