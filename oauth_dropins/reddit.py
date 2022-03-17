"""reddit OAuth drop-in.

reddit API docs:
https://github.com/reddit-archive/reddit/wiki/API
https://www.reddit.com/dev/api
https://www.reddit.com/prefs/apps

praw API docs:
https://praw.readthedocs.io/en/v3.6.0/pages/oauth.html
"""
import logging
import urllib.parse

from flask import request
from google.cloud import ndb
import praw

from . import views, models
from .webutil import appengine_info, flask_util, util
from .webutil.util import json_dumps, json_loads

from random import randint

logger = logging.getLogger(__name__)

if appengine_info.DEBUG:
  REDDIT_APP_KEY = util.read('reddit_app_key_local')
  REDDIT_APP_SECRET = util.read('reddit_app_secret_local')
else:
  REDDIT_APP_KEY = util.read('reddit_app_key')
  REDDIT_APP_SECRET = util.read('reddit_app_secret')


class RedditAuth(models.BaseAuth):
  """An authenticated reddit user.

  Provides methods that return information about this user and make OAuth-signed
  requests to the Tumblr API. Stores OAuth credentials in the datastore. See
  models.BaseAuth for usage details.

  reddit-specific details: implements "access_token," which is really a refresh_token
  see: https://stackoverflow.com/questions/28955541/how-to-get-access-token-reddit-api
  The datastore entity key name is the reddit username.
  """
  # refresh token
  refresh_token = ndb.StringProperty(required=True)
  user_json = ndb.TextProperty()

  def site_name(self):
    return 'Reddit'

  def user_display_name(self):
    """Returns the username.
    """
    return self.key_id()


class Start(views.Start):
  """Starts reddit auth. goes directly to redirect. passes to_path in "state"
  """
  NAME = 'reddit'
  LABEL = 'Reddit'
  DEFAULT_SCOPE = 'identity,read'

  def redirect_url(self, state=None):
    # if state is None the reddit API redirect breaks, set to random string
    if not state:
      state = str(randint(100000, 999999))
    assert REDDIT_APP_KEY and REDDIT_APP_SECRET, \
      "Please fill in the reddit_app_key and reddit_app_secret files in your app's root directory."
    url = urllib.parse.urljoin(request.host_url, self.to_path)
    reddit = praw.Reddit(client_id=REDDIT_APP_KEY,
                         client_secret=REDDIT_APP_SECRET,
                         redirect_uri=url,
                         user_agent=util.user_agent)

    # store the state for later use in the callback view
    models.OAuthRequestToken(id=state,
                             token_secret=state,
                             state=state).put()
    st = util.encode_oauth_state({'state': state, 'to_path': self.to_path})
    return reddit.auth.url(self.scope.split(self.SCOPE_SEPARATOR), st, 'permanent')

  @classmethod
  def button_html(cls, *args, **kwargs):
    return super(cls, cls).button_html(
      *args,
      input_style='background-color: #CEE3F8; padding: 10px',
      **kwargs)


class Callback(views.Callback):
  """OAuth callback. Only ensures that identity access was granted.
  """

  def dispatch_request(self):
    error = request.values.get('error')
    st = util.decode_oauth_state(request.values.get('state'))
    state = st.get('state')
    to_path = st.get('to_path')
    code = request.values.get('code')
    if error or not state or not code:
      if error in ('access_denied'):
        logger.info(f"User declined: {request.values.get('error_description')}")
        return self.finish(None, state=state)
      else:
        flask_util.error(error)

    # look up the stored state to check authenticity
    request_token = models.OAuthRequestToken.get_by_id(state)
    if request_token is None:
      flask_util.error(f'Invalid oauth_token: {state}')

    url = urllib.parse.urljoin(request.host_url, to_path)
    reddit = praw.Reddit(client_id=REDDIT_APP_KEY,
                         client_secret=REDDIT_APP_SECRET,
                         redirect_uri=url,
                         user_agent=util.user_agent)

    refresh_token = reddit.auth.authorize(code)
    praw_user = reddit.user.me()
    user_json = praw_to_user(praw_user)
    user_id = user_json.get('name')

    auth = RedditAuth(id=user_id,
                      refresh_token=refresh_token,
                      user_json=json_dumps(user_json))
    auth.put()
    return self.finish(auth, state=state)


def praw_to_user(user):
  """
  Converts a PRAW user to a dict user.

  Args:
    user: :class:`praw.models.Redditor`

  Note 1: accessing redditor attributes lazily calls reddit API
  Note 2: if user.is_suspended is True, other attributes will not exist
  Note 3: subreddit refers to a user profile (stored as a subreddit)
  Ref: https://praw.readthedocs.io/en/latest/code_overview/models/redditor.html

  Returns: dict

  Raises:
    :class:`prawcore.exceptions.NotFound` if the user doesn't exist or has been
    deleted
  """
  if getattr(user, 'is_suspended', False):
    return {}

  subreddit = getattr(user, 'subreddit', None)
  if subreddit:
    subreddit = {
      'id': getattr(subreddit, 'id', None),
      'display_name': getattr(subreddit, 'display_name', None),
      'name': getattr(subreddit, 'name', None),
      'description': getattr(subreddit, 'public_description', None),
    }

  return {
    'name': getattr(user, 'name', None),
    'subreddit': subreddit,
    'icon_img': getattr(user, 'icon_img', None),
    'id': getattr(user, 'id', None),
    'created_utc': getattr(user, 'created_utc', None)
  }
