"""Example oauth-dropins app. Serves the front page and discovery files.
"""
import importlib
import logging
import urllib.parse

from flask import Flask, render_template, request
import flask
import flask_gae_static
from google.cloud import ndb
from oauth_dropins.webutil import flask_util, util
import requests
from werkzeug.exceptions import HTTPException

from oauth_dropins.webutil import appengine_info, appengine_config

logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=None)
app.json.compact = False
app.config.from_pyfile('config.py')
app.wsgi_app = flask_util.ndb_context_middleware(
    app.wsgi_app, client=appengine_config.ndb_client)
if appengine_info.DEBUG:
  flask_gae_static.init_app(app)

logging.getLogger('requests_oauthlib').setLevel(logging.DEBUG)


SITES = {name: importlib.import_module(f'oauth_dropins.{name}') for name in (
    'blogger',
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
    'medium',
    'meetup',
    'pixelfed',
    'reddit',
    'tumblr',
    'twitter',
    'wordpress_rest',
  )}
from oauth_dropins import google_signin
google_signin.Start.INCLUDE_GRANTED_SCOPES = False


for site, module in SITES.items():
  start = f'/{site}/start'
  callback = f'/{site}/oauth_callback'
  app.add_url_rule(start, view_func=module.Start.as_view(start, callback),
                   methods=['POST'])
  app.add_url_rule(callback, view_func=module.Callback.as_view(callback, '/'))


@app.errorhandler(Exception)
def handle_discovery_errors(e):
  """A Flask exception handler that handles URL discovery errors.

  Used to catch Mastodon and IndieAuth connection failures, etc.
  """
  if isinstance(e, HTTPException):
    return e

  if isinstance(e, (ValueError, requests.RequestException)):
    logger.warning('', exc_info=True)
    return flask.redirect('/?' + urllib.parse.urlencode({'error': str(e)}))

  return flask_util.handle_exception(e)


@app.route('/')
def home_page():
  """Renders and serves the home page."""
  vars = dict(request.args)
  vars.update({
    site + '_html': module.Start.button_html(
      '/%s/start' % site, image_prefix='/static/',
      outer_classes='col-md-3 col-sm-4 col-xs-6')
    for site, module in SITES.items()
  })

  key = request.args.get('auth_entity')
  if key:
    vars['entity'] = ndb.Key(urlsafe=key).get()

  return render_template('index.html', **vars)
