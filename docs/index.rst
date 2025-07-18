oauth-dropins
-------------

This is a collection of drop-in Python
`Flask <https://flask.palletsprojects.com/>`__ views for the initial
`OAuth <http://oauth.net/>`__ client flows for many popular sites,
including Blogger, Bluesky, Disqus, Dropbox, Facebook, Flickr, GitHub,
Google, IndieAuth, Instagram, LinkedIn, Mastodon, Medium, Tumblr,
Twitter, and WordPress.com.

oauth-dropins stores user credentials in `Google Cloud
Datastore <https://cloud.google.com/datastore/>`__. It’s primarily
designed for `Google App Engine <https://appengine.google.com/>`__, but
it can be used in any Python web application, regardless of host or
framework.

- `Available on PyPi. <https://pypi.python.org/pypi/oauth-dropins/>`__
  Install with ``pip install oauth-dropins``.
- `Getting started docs. <#quick-start>`__
- `Reference
  docs. <https://oauth-dropins.readthedocs.io/en/latest/source/oauth_dropins.html>`__
- Demo app at
  `oauth-dropins.appspot.com <http://oauth-dropins.appspot.com/>`__.
- `Source code on GitHub. <https://github.com/snarfed/oauth-dropins/>`__

This software is released into the public domain. See LICENSE for
details.

Quick start
-----------

Here’s a full example of using the GitHub drop-in.

1. Install oauth-dropins with ``pip install oauth-dropins``.

2. Put your `GitHub OAuth
   application’s <https://docs.github.com/en/developers/apps/building-oauth-apps/creating-an-oauth-app>`__
   ID and secret in two plain text files in your app’s root directory,
   ``github_client_id`` and ``github_client_secret``. (If you use git,
   you’ll probably also want to add them to your ``.gitignore``.)

3. Create a ``github_oauth.py`` file with these contents:

   .. code:: python

      from oauth_dropins import github
      from app import app  # ...or wherever your Flask app is

      app.add_url_rule('/start',
                       view_func=github.Start.as_view('start', '/callback'),
                       methods=['POST'])
      app.add_url_rule('/callback',
                       view_func=github.Callback.as_view('callback', '/after'))

Voila! Send your users to ``/github/start`` when you want them to
connect their GitHub account to your app, and when they’re done, they’ll
be redirected to ``/after?access_token=...`` in your app.

All of the sites provide the same API. To use a different one, just
import the site module you want and follow the same steps. The filenames
for app keys and secrets also differ by site; see each site’s ``.py``
file for its filenames.

Usage details
-------------

There are three main parts to an OAuth drop-in: the initial redirect to
the site itself, the redirect back to your app after the user approves
or declines the request, and the datastore entity that stores the user’s
OAuth credentials and helps you use them. These are implemented by
`Start <#start>`__ and ```Callback`` <#callback>`__, which are
`Flask <https://flask.palletsprojects.com/>`__
`View <https://flask.palletsprojects.com/en/2.0.x/api/#flask.views.View>`__
classes, and `auth entities <#auth-entities>`__, which are `Google Cloud
Datastore <https://cloud.google.com/datastore/>`__ `ndb
models <https://googleapis.dev/python/python-ndb/latest/model.html>`__.

``Start``
~~~~~~~~~

This view class redirects you to an OAuth-enabled site so it can ask the
user to grant your app permission. It has two useful methods:

- The constructor, ``__init__(self, to_path, scopes=None)``. ``to_path``
  is the OAuth callback, ie URL path on your site that the site’s OAuth
  flow should redirect back to after it’s done. This is handled by a
  `Callback <#callback>`__ view in your application, which needs to
  handle the ``to_path`` route.

  If you want to add OAuth scopes beyond the default one(s) needed for
  login, you can pass them to the ``scopes`` kwarg as a string or
  sequence of strings, or include them in the ``scopes`` query parameter
  in the POST request body. This is supported in most sites, but not
  all.

  Some OAuth 1 sites support alternatives to scopes. For Twitter, the
  ``Start`` constructor takes an additional ``access_type`` kwarg that
  may be ``read`` or ``write``. It’s passed through to Twitter
  `x_auth_access_type <https://dev.twitter.com/docs/api/1/post/oauth/request_token>`__.
  For Flickr, ``Start`` accepts a ``perms`` POST query parameter that
  may be ``read``, ``write`` or ``delete``; it’s `passed through to
  Flickr <https://www.flickr.com/services/api/auth.oauth.html#authorization>`__
  unchanged. (Flickr claims it’s optional, but `sometimes breaks if it’s
  not
  provided. <http://stackoverflow.com/questions/6517317/flickr-api-error-when-oauth>`__)

- ``redirect_url(state=None)`` returns the URL to redirect to at the
  site to initiate the OAuth flow. ``Start`` will redirect here
  automatically if it’s used in a WSGI application, but you can call
  this manually if you want to control that redirect yourself:

.. code:: python

   import flask

   class MyView(Start):
     def dispatch_request(self):
       ...
       flask.redirect(self.redirect_url())

``Callback``
~~~~~~~~~~~~

This class handles the HTTP redirect back to your app after the user has
granted or declined permission. It also has two useful methods:

- The constructor, ``__init__(self, to_path, scopes=None)``. ``to_path``
  is the URL path on your site that users should be redirected to after
  the callback view is done. It will include a ``state`` query parameter
  with the value provided to ``Start``. It will also include an OAuth
  token in its query parameters, either ``access_token`` for OAuth 2.0
  or ``access_token_key`` and ``access_token_secret`` for OAuth 1.1. It
  will also include an ``auth_entity`` query parameter with the string
  key of an `auth entity <#auth-entities>`__ that has more data (and
  functionality) for the authenticated user. If the user declined the
  OAuth authorization request, the only query parameter besides
  ``state`` will be ``declined=true``.

- ``finish(auth_entity, state=None)`` is run in the initial callback
  request after the OAuth response has been processed. ``auth_entity``
  is the newly created auth entity for this connection, or ``None`` if
  the user declined the OAuth authorization request.

  By default, ``finish`` redirects to ``to_path``, but you can subclass
  ``Callback`` and override it to run your own code instead of
  redirecting:

.. code:: python

   class MyCallback(github.Callback):
     def finish(self, auth_entity, state=None):
       super().finish(auth_entity, state=state)  # ignore returned redirect
       self.response.write('Hi %s, thanks for connecting your %s account.' %
           (auth_entity.user_display_name(), auth_entity.site_name()))

Auth entities
~~~~~~~~~~~~~

Each site defines a Google Cloud Datastore `ndb.Model
class <https://developers.google.com/appengine/docs/python/datastore/entities#Python_Kinds_and_identifiers>`__
that stores each user’s OAuth credentials and other useful information,
like their name and profile URL. The class name is generally of the form
SiteAuth, e.g. ``GitHubAuth``. Here are the useful methods:

- ``site_name()`` returns the human-readable string name of the site,
  e.g. “Facebook”.

- ``user_display_name()`` returns a human-readable string name for the
  user, e.g. “Ryan Barrett”. This is usually their first name, full
  name, or username.

- ``access_token()`` returns the OAuth access token. For OAuth 2 sites,
  this is a single string. For OAuth 1.1 sites (currently just Twitter,
  Tumblr, and Flickr), this is a ``(string key, string secret)`` tuple.

The following methods are optional. Auth entity classes usually
implement at least one of them, but not all.

- ``api()`` returns a site-specific API object. This is usually a third
  party library dedicated to the site,
  e.g. `Tweepy <https://github.com/tweepy/tweepy>`__ or
  `python-instagram <https://github.com/Instagram/python-instagram>`__.
  See the site class’s docstring for details.

- ``urlopen(data=None, timeout=None)`` wraps ``urlopen()`` and adds the
  OAuth credentials to the request. Use this for making direct HTTP
  request to a site’s REST API. Some sites may provide ``get()``
  instead, which wraps ``requests.get()``.

Flask session
~~~~~~~~~~~~~

Troubleshooting/FAQ
-------------------

1. If you get this error:

   ::

      bash: ./bin/easy_install: ...bad interpreter: No such file or directory

You’ve probably hit `this virtualenv
bug <https://github.com/pypa/virtualenv/issues/53>`__: virtualenv
doesn’t support paths with spaces.

The easy fix is to recreate the virtualenv in a path without spaces. If
you can’t do that, then after creating the virtualenv, but before
activating it, edit the activate, easy_install and pip files in
``local/bin/`` to escape any spaces in the path.

For example, in ``activate``, ``VIRTUAL_ENV=".../has space/local"``
becomes ``VIRTUAL_ENV=".../has\ space/local"``, and in ``pip`` and
``easy_install`` the first line changes from
``#!".../has space/local/bin/python"`` to
``#!".../has\ space/local/bin/python"``.

This should get virtualenv to install in the right place. If you do this
wrong at first, you’ll have installs in eg
``/usr/local/lib/python3.7/site-packages`` that you need to delete,
since they’ll prevent virtualenv from installing into the local
``site-packages``.

1. If you see errors importing or using ``tweepy``, it may be because
   ``six.py`` isn’t installed. Try ``pip install six`` manually.
   ``tweepy`` does include ``six`` in its dependencies, so this
   shouldn’t be necessary. Please `let us
   know <https://github.com/snarfed/oauth-dropins/issues>`__ if it
   happens to you so we can debug!

2. If you get an error like this:

   ::

      Running setup.py develop for gdata
      ...
      error: option --home not recognized
      ...
      InstallationError: Command /usr/bin/python -c "import setuptools, tokenize; __file__='/home/singpolyma/src/bridgy/src/gdata/setup.py'; exec(compile(getattr(tokenize, 'open', open)(__file__).read().replace('\r\n', '\n'), __file__, 'exec'))" develop --no-deps --home=/tmp/tmprBISz_ failed with error code 1 in .../src/gdata

…you may be hitting `Pip bug
1833 <https://github.com/pypa/pip/issues/1833>`__. Are you passing
``-t`` to ``pip install``? Use the virtualenv instead, it’s your friend.
If you really want ``-t``, try removing the ``-e`` from the lines in
``requirements.txt`` that have it.

Changelog
---------

6.7 - 2025-07-08
~~~~~~~~~~~~~~~~

- Bluesky:

  - Add ``$type: app.bsky.actor.defs#profileViewDetailed`` to
    ``BlueskyAuth.user_json``.
  - Add new ``BlueskyAuth.oauth_api`` method.
  - Remove invisible Unicode characters from handle
    (`bluesky-social/social-app#8451 <https://github.com/bluesky-social/social-app/issues/8451>`__).

- Mastodon:

  - Change default
    `scope <https://docs.joinmastodon.org/api/oauth-scopes/>`__ from
    ``read:accounts`` to ``profile``.
  - Add new ``MastodonAuth.actor_id`` method.

- Pixelfed:

  - Add new ``PixelfedAuth.actor_id`` method.

- Add optional ``auth`` arg to ``logout`` to only log out a single
  account.
- WordPress:

  - Handle blog without valid URL.

.. _section-1:

6.6 - 2025-03-13
~~~~~~~~~~~~~~~~

- Add `Bluesky
  OAuth <https://docs.bsky.app/docs/advanced-guides/oauth-client>`__.
- Add `Threads <https://developers.facebook.com/docs/threads/>`__.
- Store logins in the Flask session. Add new top-level ``get_logins``
  and ``logout`` functions.
- Add new ``pds_url`` attribute to ``BlueskyAuth``.
- Add new ``BaseAuth.image_url`` method.

.. _section-2:

6.5 - 2025-01-01
~~~~~~~~~~~~~~~~

- IndieAuth:

  - Bug fix: handle relative URLs in ``Link`` headers. (Thanks
    `catgirlinspace <https://catgirlin.space/>`__!)

.. _section-3:

6.4 - 2024-06-24
~~~~~~~~~~~~~~~~

Misc webutil updaates.

.. _section-4:

6.3 - 2024-03-15
~~~~~~~~~~~~~~~~

- Bluesky:

  - Normalize handles to lower case, remove leading ``@``
    (`bridgy#1667 <https://github.com/snarfed/bridgy/issues/1667>`__).

Miscellaneous changes in ``webutil``.

.. _section-5:

6.2 - 2023-09-15
~~~~~~~~~~~~~~~~

Miscellaneous changes in ``webutil``.

.. _section-6:

6.1 - 2023-03-22
~~~~~~~~~~~~~~~~

*Non-breaking changes:*

- IndieAuth:

  - Store access token and refresh token in ``IndieAuth`` datastore
    entities.

- Flickr:

  - Handle errors from initial OAuth 1.0 authorization request.

.. _section-7:

6.0 - 2022-12-03
~~~~~~~~~~~~~~~~

*Breaking changes:*

- Remove ``webutil.handlers``, which was based on the largely
  unmaintained
  `webapp2 <https://github.com/GoogleCloudPlatform/webapp2>`__. All
  known clients have migrated to
  `Flask <https://palletsprojects.com/p/flask/>`__ and
  ``webutil.flask_util``.
- Drop Python 3.6 support. Python 3.7 is now the minimum required
  version.

*Non-breaking changes:*

- Add new ``twitter_v2`` module for Twitter’s new `OAuth 2 with
  PKCE <https://developer.twitter.com/en/docs/authentication/oauth-2-0/authorization-code>`__
  support and `v2
  API <https://developer.twitter.com/en/docs/twitter-api/migrate/whats-new>`__.
- IndieAuth:

  - Add support for `authorization
    endpoints <https://indieauth.spec.indieweb.org/#authorization-endpoint>`__,
    along with existing `token
    endpoint <https://indieauth.spec.indieweb.org/#token-endpoint>`__
    support. Thanks `@jamietanna <https://www.jvt.me/>`__!
    (`#284 <https://github.com/snarfed/oauth-dropins/pull/284>`__)

- Blogger:

  - Fix bug when user approves the OAuth prompt but has no Blogger
    blogs. Instead of crashing, we now redirect to the callback with
    ``declined=True``, which is still wrong, but less bad.

- Mastodon:

  - Change ``MastodonAuth.access_token_str`` from ndb ``TextProperty``
    to ``StringProperty`` so that it’s indexed in the Datastore.
  - When the callback gets an invalid ``state`` parameter, return HTTP
    400 instead of raising ``JSONDecodeError``.

- Misc webutil updates.

.. _section-8:

5.0 - 2022-03-23
~~~~~~~~~~~~~~~~

*Breaking changes:*

- Drop Python 3.5 support. Python 3.6 is now the minimum required
  version.

*Non-breaking changes:*

- Switch from app_server to ``flask run`` for local development.
- Add ``webutil.util.set_user_agent`` to set ``User-Agent`` header to be
  sent with all HTTP requests.

.. _section-9:

4.0 - 2021-09-15
~~~~~~~~~~~~~~~~

*Breaking changes:*

- Migrate from
  `webapp2 <https://github.com/GoogleCloudPlatform/webapp2/>`__ to
  `Flask <https://flask.palletsprojects.com/>`__. webapp2 had a good
  run, but it’s no longer actively developed, and Flask is one of the
  most widely adopted standalone web frameworks in the Python community.

- Remove ``to()`` class methods. Instead, now pass redirect paths to
  Flask’s ``as_view()`` function, eg:

  .. code:: py

     app = Flask()
     app.add_url_rule('/start', view_func=twitter.Callback.as_view('start', '/oauth_callback'))

- Remove deprecated ``blogger_v2`` module alias.

- ``webutil``: migrate webapp2 HTTP request handlers in the ``handlers``
  module - ``XrdOrJrdHandler``, ``HostMetaHandler``, and
  ``HostMetaXrdsHandler`` - to Flask views in a new ``flask_util``
  module.

*Non-breaking changes:*

- ``webutil``: implement `Webmention <https://webmention.net/>`__
  protocol in new ``webmention`` module.
- ``webutil``: add misc Flask utilities and helpers in new
  ``flask_util`` module.

.. _section-10:

3.1 - 2021-04-03
~~~~~~~~~~~~~~~~

- Add Python 3.8 support, drop 3.3 and 3.4. Python 3.5 is now the
  minimum required version.
- Add `Pixelfed <https://pixelfed.org/>`__ support, heavily based on
  Mastodon.
- Add `Reddit <https://pixelfed.org/>`__ support. Thanks `Will
  Stedden <https://bonkerfield.org/>`__!
- WordPress.com:

  - Handle errors from access token request.

.. _section-11:

3.0 - 2020-03-14
~~~~~~~~~~~~~~~~

*Breaking changes:*

- *Python 2 is no longer supported!* Including the `App Engine Standard
  Python 2
  runtime <https://cloud.google.com/appengine/docs/standard/python/>`__.
  On the plus side, the `Python 3
  runtimes <https://cloud.google.com/appengine/docs/standard/python3/>`__,
  both
  `Standard <https://cloud.google.com/appengine/docs/standard/python3/>`__
  and
  `Flexible <https://cloud.google.com/appengine/docs/flexible/python/>`__,
  are now supported.
- Replace ``handlers.memcache_response()``, which used Python 2 App
  Engine’s memcache service, with ``cache_response()``, which uses local
  runtime memory.
- Remove the ``handlers.TemplateHandler.USE_APPENGINE_WEBAPP`` toggle to
  use Python 2 App Engine’s ``google.appengine.ext.webapp2.template``
  instead of Jinja.
- Blogger:

  - Login is now based on `Google
    Sign-In <https://developers.google.com/identity/>`__. The
    ``api_from_creds()``, ``creds()``, and ``http()`` methods have been
    removed. Use the remaining ``api()`` method to get a
    ``BloggerClient``, or ``access_token()`` to make API calls manually.

- Google:

  - Replace ``GoogleAuth`` with the new ``GoogleUser`` NDB model class,
    which `doesn’t depend on the deprecated
    oauth2client <https://google-auth.readthedocs.io/en/latest/oauth2client-deprecation.html>`__.
  - Drop ``http()`` method (which returned an ``httplib2.Http``).

- Mastodon:

  - ``StartHandler``: drop ``APP_NAME``/``APP_URL`` class attributes and
    ``app_name``/``app_url`` kwargs in the ``to()`` method and replace
    them with new ``app_name()``/``app_url()`` methods that subclasses
    should override, since they often depend on WSGI environment
    variables like ``HTTP_HOST`` and ``SERVER_NAME`` that are available
    during requests but not at runtime startup.

- ``webutil``:

  - Drop ``handlers.memcache_response()`` since the Python 3 runtime
    doesn’t include memcache.
  - Drop ``handlers.TemplateHandler`` support for ``webapp2.template``
    via ``USE_APPENGINE_WEBAPP``, since the Python 3 runtime doesn’t
    include ``webapp2`` built in.
  - Remove ``cache`` and ``fail_cache_time_secs`` kwargs from
    ``util.follow_redirects()``. Caching is now built in. You can bypass
    the cache with ``follow_redirects.__wrapped__()``.
    `Details. <https://cachetools.readthedocs.io/en/stable/#cachetools.cached>`__

Non-breaking changes:

- Add Meetup support. (Thanks `Jamie Tanna <https://www.jvt.me/>`__!)
- Blogger, Google:

  - The ``state`` query parameter now works!

- Add new ``outer_classes`` kwarg to ``button_html()`` for the outer
  ``<div>``, eg as Bootstrap columns.
- Add new ``image_file`` kwarg to ``StartHandler.button_html()``

.. _section-12:

2.2 - 2019-11-01
~~~~~~~~~~~~~~~~

- Add LinkedIn and Mastodon!
- Add Python 3.7 support, and improve overall Python 3 compatibility.
- Add new ``button_html()`` method to all ``StartHandler`` classes.
  Generates the same button HTML and styling as on
  `oauth-dropins.appspot.com <https://oauth-dropins.appspot.com/>`__.
- Blogger: rename module from ``blogger_v2`` to ``blogger``. The
  ``blogger_v2`` module name is still available as an alias, implemented
  via symlink, but is now deprecated.
- Dropbox: fix crash with unicode header value.
- Google: fix crash when user object doesn’t have ``name`` field.
- Facebook: `upgrade Graph API version from 2.10 to
  4.0. <https://developers.facebook.com/docs/graph-api/changelog>`__
- Update a number of dependencies.
- Switch from Python’s built in ``json`` module to
  `ujson <https://github.com/esnme/ultrajson/>`__ (built into App
  Engine) to speed up JSON parsing and encoding.

.. _section-13:

2.0 - 2019-02-25
~~~~~~~~~~~~~~~~

- *Breaking change*: switch from `Google+
  Sign-In <https://developers.google.com/+/web/signin/>`__ (`which shuts
  down in March <https://developers.google.com/+/api-shutdown>`__) to
  `Google Sign-In <https://developers.google.com/identity/>`__. Notably,
  this removes the ``googleplus`` module and adds a new
  ``google_signin`` module, renames the ``GooglePlusAuth`` class to
  ``GoogleAuth``, and removes its ``api()`` method. Otherwise, the
  implementation is mostly the same.
- webutil.logs: return HTTP 400 if ``start_time`` is before 2008-04-01
  (App Engine’s rough launch window).

.. _section-14:

1.14 - 2018-11-12
~~~~~~~~~~~~~~~~~

- Fix dev_appserver in Cloud SDK 219 / ``app-engine-python`` 1.9.76 and
  onward.
  `Background. <https://issuetracker.google.com/issues/117145272#comment25>`__
- Upgrade ``google-api-python-client`` from 1.6.3 to 1.7.4 to `stop
  using the global HTTP Batch
  endpoint <https://developers.googleblog.com/2018/03/discontinuing-support-for-json-rpc-and.html>`__.
- Other minor internal updates.

.. _section-15:

1.13 - 2018-08-08
~~~~~~~~~~~~~~~~~

- IndieAuth: support JSON code verification responses as well as
  form-encoded
  (`snarfed/bridgy#809 <https://github.com/snarfed/bridgy/issues/809>`__).

.. _section-16:

1.12 - 2018-03-24
~~~~~~~~~~~~~~~~~

- More Python 3 updates and bug fixes in webutil.util.

.. _section-17:

1.11 - 2018-03-08
~~~~~~~~~~~~~~~~~

- Add GitHub!
- Facebook:

  - Pass ``state`` to the initial OAuth endpoint directly, instead of
    encoding it into the redirect URL, so the redirect can `match the
    Strict Mode
    whitelist <https://developers.facebook.com/blog/post/2017/12/18/strict-uri-matching/>`__.

- Add Python 3 support to webutil.util!
- Add humanize dependency for webutil.logs.

.. _section-18:

1.10 - 2017-12-10
~~~~~~~~~~~~~~~~~

Mostly just internal changes to webutil to support granary v1.10.

.. _section-19:

1.9 - 2017-10-24
~~~~~~~~~~~~~~~~

Mostly just internal changes to webutil to support granary v1.9.

- Flickr:

  - Handle punctuation in error messages.

.. _section-20:

1.8 - 2017-08-29
~~~~~~~~~~~~~~~~

- Facebook:

  - Upgrade Graph API from v2.6 to v2.10.

- Flickr:

  - Fix broken ``FlickrAuth.urlopen()`` method.

- Medium:

  - Bug fix for Medium OAuth callback error handling.

- IndieAuth:

  - Store authorization endpoint in state instead of rediscovering it
    from ``me`` parameter, `which is going
    away <https://github.com/aaronpk/IndieAuth.com/issues/167>`__.

.. _section-21:

1.7 - 2017-02-27
~~~~~~~~~~~~~~~~

- Updates to bundled webutil library, notably WideUnicode class.

.. _section-22:

1.6 - 2016-11-21
~~~~~~~~~~~~~~~~

- Add auto-generated docs with Sphinx. Published at
  `oauth-dropins.readthedocs.io <http://oauth-dropins.readthedocs.io/>`__.
- Fix Dropbox bug with fetching access token.

.. _section-23:

1.5 - 2016-08-25
~~~~~~~~~~~~~~~~

- Add `Medium <https://medium.com/>`__.

.. _section-24:

1.4 - 2016-06-27
~~~~~~~~~~~~~~~~

- Upgrade Facebook API from v2.2 to v2.6.

.. _section-25:

1.3 - 2016-04-07
~~~~~~~~~~~~~~~~

- Add `IndieAuth <https://indieauth.com/>`__.
- More consistent logging of HTTP requests.
- Set up Coveralls.

.. _section-26:

1.2 - 2016-01-11
~~~~~~~~~~~~~~~~

- Flickr:

  - Add upload method.
  - Improve error handling and logging.

- Bug fixes and cleanup for constructing scope strings.
- Add developer setup and troubleshooting docs.
- Set up CircleCI.

.. _section-27:

1.1 - 2015-09-06
~~~~~~~~~~~~~~~~

- Flickr: split out flickr_auth.py file.
- Add a number of utility functions to webutil.

.. _section-28:

1.0 - 2015-06-27
~~~~~~~~~~~~~~~~

- Initial PyPi release.

Development
-----------

Pull requests are welcome! Feel free to `ping me in
#indieweb-dev <https://indieweb.org/discuss>`__ with any questions.

First, fork and clone this repo. Then, install the `Google Cloud
SDK <https://cloud.google.com/sdk/>`__ and run
``gcloud components install cloud-firestore-emulator`` to install the
`Firestore
emulator <https://cloud.google.com/firestore/docs/emulator>`__. Once you
have them, set up your environment by running these commands in the repo
root directory:

.. code:: shell

   gcloud config set project oauth-dropins
   git submodule init
   git submodule update
   python3 -m venv local
   source local/bin/activate
   pip install -r requirements.txt

Run the demo app locally with
`flask run <https://flask.palletsprojects.com/en/2.0.x/cli/#run-the-development-server>`__:

.. code:: shell

   gcloud emulators firestore start --host-port=:8089 --database-mode=datastore-mode < /dev/null >& /dev/null &
   GAE_ENV=localdev FLASK_ENV=development flask run -p 8080

To deploy to production:

``gcloud -q beta app deploy --no-cache oauth-dropins *.yaml``

The docs are built with `Sphinx <http://sphinx-doc.org/>`__, including
`apidoc <http://www.sphinx-doc.org/en/stable/man/sphinx-apidoc.html>`__,
`autodoc <http://www.sphinx-doc.org/en/stable/ext/autodoc.html>`__, and
`napoleon <http://www.sphinx-doc.org/en/stable/ext/napoleon.html>`__.
Configuration is in
`docs/conf.py <https://github.com/snarfed/oauth-dropins/blob/master/docs/conf.py>`__
To build them, first install Sphinx with ``pip install sphinx``. (You
may want to do this outside your virtualenv; if so, you’ll need to
reconfigure it to see system packages with
``python3 -m venv --system-site-packages local``.) Then, run
`docs/build.sh <https://github.com/snarfed/oauth-dropins/blob/master/docs/build.sh>`__.

Release instructions
--------------------

Here’s how to package, test, and ship a new release. (Note that this is
`largely duplicated in granary’s readme
too <https://github.com/snarfed/granary#release-instructions>`__.)

1.  Run the unit tests.
    ``sh     source local/bin/activate.csh     gcloud emulators firestore start --host-port=:8089 --database-mode=datastore-mode < /dev/null >& /dev/null &     sleep 2s     python -m unittest discover     kill %1     deactivate``
2.  Bump the version number in ``setup.py`` and ``docs/conf.py``.
    ``git grep`` the old version number to make sure it only appears in
    the changelog. Change the current changelog entry in ``README.md``
    for this new version from *unreleased* to the current date.
3.  Build the docs. If you added any new modules, add them to the
    appropriate file(s) in ``docs/source/``. Then run
    ``./docs/build.sh``.
4.  ``git commit -am 'release vX.Y'``
5.  Upload to `test.pypi.org <https://test.pypi.org/>`__ for testing.
    ``sh     python setup.py clean build sdist     setenv ver X.Y     source local/bin/activate.csh     twine upload -r pypitest dist/oauth_dropins-$ver.tar.gz``
6.  Install from test.pypi.org.
    ``sh     cd /tmp     python -m venv local     source local/bin/activate.csh     pip install --upgrade pip     # mf2py 1.1.2 on test.pypi.org is broken :(     pip install mf2py     pip install -i https://test.pypi.org/simple --extra-index-url https://pypi.org/simple oauth-dropins     deactivate``
7.  Smoke test that the code trivially loads and runs.
    ``sh     source local/bin/activate.csh     python     # run test code below     deactivate``
    Test code to paste into the interpreter:
    ``py     from oauth_dropins.webutil import util     util.__file__     util.UrlCanonicalizer()('http://asdf.com')     # should print 'https://asdf.com/'     exit()``
8.  Tag the release in git. In the tag message editor, delete the
    generated comments at bottom, leave the first line blank (to omit
    the release “title” in github), put ``### Notable changes`` on the
    second line, then copy and paste this version’s changelog contents
    below it.
    ``sh     git tag -a v$ver --cleanup=verbatim     git push     git push --tags``
9.  `Click here to draft a new release on
    GitHub. <https://github.com/snarfed/oauth-dropins/releases/new>`__
    Enter ``vX.Y`` in the *Tag version* box. Leave *Release title*
    empty. Copy ``### Notable changes`` and the changelog contents into
    the description text box.
10. Upload to `pypi.org <https://pypi.org/>`__!
    ``sh     twine upload dist/oauth_dropins-$ver.tar.gz``

Related work
------------

- `Loginpass <https://github.com/authlib/loginpass>`__/`Authlib <https://authlib.org/>`__
- `Authomatic <https://authomatic.github.io/authomatic/>`__
- `Python Social
  Auth <https://python-social-auth.readthedocs.io/en/latest/>`__
- `Authl <https://authl.readthedocs.io/en/stable/>`__
