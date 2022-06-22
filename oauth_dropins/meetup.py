"""Meetup.com drop-in.

API docs:
https://www.meetup.com/meetup_api/
"""
import logging
import urllib.parse

from flask import request
from google.cloud import ndb

from . import views
from .models import BaseAuth
from .webutil import appengine_info, flask_util, util
from .webutil.util import json_loads

logger = logging.getLogger(__name__)

if appengine_info.DEBUG:
    MEETUP_CLIENT_ID = util.read('meetup_client_id_local')
    MEETUP_CLIENT_SECRET = util.read('meetup_client_secret_local')
else:
    MEETUP_CLIENT_ID = util.read('meetup_client_id')
    MEETUP_CLIENT_SECRET = util.read('meetup_client_secret')

GET_AUTH_CODE_URL = '&'.join((
    'https://secure.meetup.com/oauth2/authorize?client_id=%(client_id)s',
    'response_type=code',
    'redirect_uri=%(redirect_uri)s',
    'scope=%(scope)s',
    'state=%(state)s',
))

GET_ACCESS_TOKEN_URL = 'https://secure.meetup.com/oauth2/access'
GET_USER_INFO_URL = 'https://api.meetup.com/members/self/'


def urlopen_bearer_token(url, access_token, data=None, **kwargs):
    """Wraps urlopen() and adds OAuth credentials to the request.
    """
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        return util.urlopen(urllib.request.Request(url, headers=headers, data=data), **kwargs)
    except BaseException as e:
        util.interpret_http_exception(e)
        raise


class MeetupAuth(BaseAuth):
    """An authenticated Meetup.com user.

    Provides methods that return information about this user and make
    OAuth-signed requests to Meetup's HTTP-based APIs. Stores OAuth credentials
    in the datastore. See models.BaseAuth for usage details.

    Implements urlopen() but not api().
    """
    access_token_str = ndb.StringProperty(required=True)
    user_json = ndb.TextProperty(required=True)

    def site_name(self):
        return 'Meetup.com'

    def user_display_name(self):
        """Returns the Meetup.com user id.
        """
        return json_loads(self.user_json)['name']

    def access_token(self):
        """Returns the OAuth access token string.
        """
        return self.access_token_str

    def urlopen(self, url, **kwargs):
        return urlopen_bearer_token(url, self.access_token_str, kwargs)


class MeetupCsrf(ndb.Model):
    """Stores a CSRF token for the Meetup.com OAuth2 flow."""
    token = ndb.StringProperty(required=False)
    state = ndb.TextProperty(required=False)


class Start(views.Start):
    """Starts Meetup.com auth. Requests an auth code and expects a redirect back.
    """

    NAME = 'meetup'
    LABEL = 'Meetup.com'
    DEFAULT_SCOPE = ''

    def redirect_url(self, state=None):

        assert MEETUP_CLIENT_ID and MEETUP_CLIENT_SECRET, \
            "Please fill in the meetup_client_id and meetup_client_secret files in your app's root directory."

        csrf_key = MeetupCsrf(state=state).put()

        return GET_AUTH_CODE_URL % {
            'client_id': MEETUP_CLIENT_ID,
            'redirect_uri': urllib.parse.quote_plus(self.to_url()),
            'scope': self.scope,
            'state': f'{urllib.parse.quote_plus(state or "")}|{csrf_key.id()}',
        }

    @classmethod
    def button_html(cls, *args, **kwargs):
        return super(cls, cls).button_html(
            *args, input_style='background-color: #EEEEEE; padding: 10px', **kwargs)


class Callback(views.Callback):
    """The auth callback. Fetches an access token, stores it, and redirects home.
    """
    def dispatch_request(self):
        # handle errors
        error = request.values.get('error')
        if error:
            if error == 'access_denied':
                logger.info('User declined')
                return self.finish(None, state=request.values.get('state'))
            else:
                flask_util.error(f"Error: {error}: {request.values.get('error_description')}")

        state = request.values['state']
        # lookup the CSRF token
        try:
            csrf_id = int(urllib.parse.unquote_plus(state).split('|')[-1])
        except (ValueError, TypeError):
            flask_util.error(f'Invalid state value {state!r}')

        csrf = MeetupCsrf.get_by_id(csrf_id)
        if not csrf:
            flask_util.error(f'No CSRF token for id {csrf_id}')

        # extract auth code and request access token
        auth_code = request.values['code']
        data = {
            'code': auth_code,
            'client_id': MEETUP_CLIENT_ID,
            'client_secret': MEETUP_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            # redirect_uri here must be the same in the oauth code request!
            # (the value here doesn't actually matter since it's requested server side.)
            'redirect_uri': request.base_url,
        }
        # TODO: handle refresh tokens
        resp = util.requests_post(GET_ACCESS_TOKEN_URL, data=data)
        resp.raise_for_status()

        logger.debug(f'Access token response: {resp}')

        try:
            data = json_loads(resp.text)
        except (ValueError, TypeError):
            logger.error(f'Bad response:\n{resp}', exc_info=True)
            flask_util.error('Bad Disqus response to access token request')

        error = data.get('error')
        if error:
            msg = f"Error: {error[0]}: {data.get('error_description')}"
            flask_util.error(msg)

        access_token = data['access_token']

        user_json = urlopen_bearer_token(GET_USER_INFO_URL, access_token).read()
        user = json_loads(user_json)
        logger.debug(f'User info response: {user}')
        user_id = str(user['id'])

        logger.info(f'Storing new Meetup account for ID: {user_id}')
        auth = MeetupAuth(id=user_id, access_token_str=access_token, user_json=user_json)
        auth.put()
        return self.finish(auth, state=csrf.state)
