"""Pixelfed OAuth drop-in.

Pixelfed's API is a clone of Mastodon's v1 API:
https://docs.pixelfed.org/technical-documentation/api-v1.html
"""
from . import mastodon


class PixelfedApp(mastodon.MastodonApp):
  """A Pixelfed API OAuth2 app registered with a specific instance."""
  pass


class PixelfedAuth(mastodon.MastodonAuth):
  """An authenticated Pixelfed user."""

  def site_name(self):
    return 'Pixelfed'


class Start(mastodon.Start):
  """Starts Pixelfed auth. Requests an auth code and expects a redirect back."""
  NAME = 'pixelfed'
  LABEL = 'Pixelfed'
  DEFAULT_SCOPE = 'read'
  APP_CLASS = PixelfedApp

  @classmethod
  def _version_ok(cls, version):
    return 'Pixelfed' in version


class Callback(mastodon.Callback):
  """The OAuth callback. Fetches an access token and stores it."""
  AUTH_CLASS = PixelfedAuth
