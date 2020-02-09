"""Meetup.com drop-in.

API docs:
https://www.meetup.com/meetup_api/
"""
import logging
import urllib.parse

from google.cloud import ndb
from webob import exc

from . import handlers
from .models import BaseAuth
from .webutil import appengine_info, util
from .webutil.util import json_loads

if appengine_info.DEBUG:
    MEETUP_CLIENT_ID = util.read('meetup_client_id_local')
    MEETUP_CLIENT_SECRET = util.read('meetup_client_secret_local')
else:
    MEETUP_CLIENT_ID = util.read('meetup_client_id')
    MEETUP_CLIENT_SECRET = util.read('meetup_client_secret')

GET_AUTH_CODE_URL = '&'.join((
    'https://secure.meetup.com/oauth2/authorize?'
    'client_id=%(client_id)s',
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
    headers = {'Authorization': 'Bearer %s' % access_token}
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

    Implements urlopen() but not http() or api().
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


class StartHandler(handlers.StartHandler):
    """Starts Meetup.com auth. Requests an auth code and expects a redirect back.
    """

    NAME = 'meetup'
    LABEL = 'Meetup.com'
    DEFAULT_SCOPE = ''

    def redirect_url(self, state=None):

        assert (MEETUP_CLIENT_ID and MEETUP_CLIENT_SECRET), (
                "Please fill in the meetup_client_id and meetup_client_secret files in "
                "your app's root directory.")

        csrf_key = MeetupCsrf(state=state).put()

        return GET_AUTH_CODE_URL % {
                'client_id': MEETUP_CLIENT_ID,
                'redirect_uri': urllib.parse.quote_plus(self.to_url()),
                'scope': self.scope,
                'state': '%s|%s' % (urllib.parse.quote_plus(state), csrf_key.id()),
                }

    @classmethod
    def button_html(cls, *args, **kwargs):
        return super(cls, cls).button_html(
                *args, input_style='background-color: #EEEEEE; padding: 10px', **kwargs)


class CallbackHandler(handlers.CallbackHandler):
    """The auth callback. Fetches an access token, stores it, and redirects home.
    """
    def get(self):
        # handle errors
        error = self.request.get('error')
        if error:
            if error == 'access_denied':
                logging.info('User declined')
                self.finish(None, state=self.request.get('state'))
                return
            else:
                msg = 'Error: %s: %s' % (error, self.request.get('error_description'))
                logging.info(msg)
                raise exc.HTTPBadRequest(msg)

        state = util.get_required_param(self, 'state')
        # lookup the CSRF token
        try:
            csrf_id = int(urllib.parse.unquote_plus(state).split('|')[-1])
        except (ValueError, TypeError):
            raise exc.HTTPBadRequest('Invalid state value %r' % state)

        csrf = MeetupCsrf.get_by_id(csrf_id)
        if not csrf:
            raise exc.HTTPBadRequest('No CSRF token for id %s' % csrf_id)

        # extract auth code and request access token
        auth_code = util.get_required_param(self, 'code')
        data = {
            'code': auth_code,
            'client_id': MEETUP_CLIENT_ID,
            'client_secret': MEETUP_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            # redirect_uri here must be the same in the oauth code request!
            # (the value here doesn't actually matter since it's requested server side.)
            'redirect_uri': self.request.path_url,
            }
        # TODO: handle refresh tokens
        resp = util.requests_post(GET_ACCESS_TOKEN_URL, data=data)
        resp.raise_for_status()

        logging.debug('Access token response: %s', resp)

        try:
            data = json_loads(resp.text)
        except (ValueError, TypeError):
            logging.error('Bad response:\n%s', resp, stack_info=True)
            raise exc.HTTPBadRequest('Bad Disqus response to access token request')

        error = data.get('error')
        if error:
            msg = 'Error: %s: %s' % (error[0], data.get('error_description'))
            logging.info(msg)
            raise exc.HTTPBadRequest(msg)

        access_token = data['access_token']

        user_json = urlopen_bearer_token(GET_USER_INFO_URL, access_token).read()
        user = json_loads(user_json)
        logging.debug('User info response: %s', user)
        user_id = str(user['id'])

        logging.info('Storing new Meetup account for ID: %s', user_id)
        auth = MeetupAuth(id=user_id, access_token_str=access_token, user_json=user_json)
        auth.put()
        self.finish(auth, state=csrf.state)
