![OAuth logo](https://raw.github.com/snarfed/oauth-dropins/master/static/oauth_shiny_128.png)
oauth-dropins
=============

This is a collection of drop-in
[Google App Engine](https://appengine.google.com/) request handlers for the
initial [OAuth](http://oauth.net/) client flows for many popular sites,
including Blogger, Disqus, Dropbox, Facebook, Flickr, Google+, Instagram,
Tumblr, Twitter, and WordPress.com.

This repo also provides an example demo app, deployed at
http://oauth-dropins.appspot.com/.

Some dependencies are included as git submodules; others are installed with
`pip` in a
[`virtualenv`](http://docs.python-guide.org/en/latest/dev/virtualenvs/).
([App Engine details.](https://cloud.google.com/appengine/docs/python/tools/libraries27#vendoring))
To get set up:

```shell
git submodule init
git submodule update
virtualenv local
source local/bin/activate
pip install -r requirements.txt
```

Then add this line to the `appengine_config.py` file in your project's root
directory:

```py
from oauth_dropins.appengine_config import *
```

This software is released into the public domain. See LICENSE for details.

Related work:

* [Python Social Auth](http://psa.matiasaguirre.net/)


Quick start
---

Here's a full example of using the Facebook drop-in.

1. Put your [Facebook application](https://developers.facebook.com/apps)'s ID
and secret in two plain text files in your app's root directory,
`facebook_app_id` and `facebook_app_secret`. (If you use git, you'll probably
also want to add them to your `.gitignore`.)

1. Create a `facebook_oauth.py` file with these contents:

```python
from oauth_dropins import facebook
import webapp2

application = webapp2.WSGIApplication([
  ('/facebook/start_oauth', facebook.StartHandler.to('/facebook/oauth_callback')),
  ('/facebook/oauth_callback', facebook.CallbackHandler.to('/next'))]
```

1. Add these lines to `app.yaml`:

```yaml
- url: /facebook/(start_oauth|oauth_callback)
  script: facebook_oauth.application
  secure: always
```

Voila! Send your users to `/facebook/start_oauth` when you want them to connect
their Facebook account to your app, and when they're done, they'll be redirected
to `/next?access_token=...` in your app.

All of the sites provide the same API. To use a different one, just import the
site module you want and follow the same steps. The filenames for app keys and
secrets also differ by site;
[`appengine_config.py`](https://github.com/snarfed/oauth-dropins/blob/master/appengine_config.py)
has the full list.


Usage details
---

There are three main parts to an OAuth drop-in: the initial redirect to the site
itself, the redirect back to your app after the user approves or declines the
request, and the datastore entity that stores the user's OAuth credentials and
helps you use them. These are implemented by [`StartHandler`](#starthandler),
[`CallbackHandler`](#callbackhandler), and [auth entities](#auth-entities),
respectively.

The request handlers are full [WSGI](http://wsgi.org/) applications and may be
used in any Python web framework that supports WSGI
([PEP 333](http://www.python.org/dev/peps/pep-0333/)). Internally, they're
implemented with [webapp2](http://webapp-improved.appspot.com/).


### `StartHandler`

This HTTP request handler class redirects you to an OAuth-enabled site so it can ask
the user to grant your app permission. It has two useful methods:

- `to(callback_path, scopes=None)` is a factory method that returns a request
  handler class you can use in a WSGI application. The argument should be the
  path mapped to [`CallbackHandler`](#callbackhandler) in your application. This
  also usually needs to match the callback URL in your app's configuration on
  the destination site.

  If you want to add OAuth scopes beyond the default one(s) needed for login,
  you can pass them to the `scopes` kwarg as a string or sequence of strings, or
  include them in the `scopes` query parameter in the POST request body. This is
  currently supported with Facebook, Google+, Blogger, and Instagram.

  Some of the sites that use OAuth 1 support alternatives. For Twitter,
  `StartHandler.to` takes an additional `access_type` kwarg that may be `read`
  or `write`. It's passed through to Twitter
  [as `x_auth_access_type`](https://dev.twitter.com/docs/api/1/post/oauth/request_token).
  For Flickr, the start handler accepts a `perms` POST query parameter that may
  be `read`, `write` or `delete`; it's
  [passed through to Flickr](https://www.flickr.com/services/api/auth.oauth.html#authorization)
  unchanged. (Flickr claims it's optional, but
  [sometimes breaks if it's not provided.](http://stackoverflow.com/questions/6517317/flickr-api-error-when-oauth))

- `redirect_url(state=None)` returns the URL to redirect to at the destination
  site to initiate the OAuth flow. `StartHandler` will redirect here
  automatically if it's used in a WSGI application, but you can also instantiate
  it and call this manually if you want to control that redirect yourself:

```python
class MyHandler(webapp2.RequestHandler):
  def get(self):
    ...
    handler_cls = facebook.StartHandler.to('/facebook/oauth_callback')
    handler = handler_cls(self.request, self.response)
    self.redirect(handler.redirect_url())
```

  However, this is *not* currently supported for Google+ and Blogger. Hopefully
  that will be fixed in the future.


### `CallbackHandler`

This class handles the HTTP redirect back to your app after the user has granted
or declined permission. It also has two useful methods:

- `to(callback_path)` is a factory method that returns a request handler class
  you can use in a WSGI application, similar to [`StartHandler`](#starthandler).
  The callback path is the path in your app that users should be redirected to
  after the OAuth flow is complete. It will include a `state` query parameter
  with the value provided by the `StartHandler`. It will also include an OAuth
  token in its query parameters, either `access_token` for OAuth 2.0 or
  `access_token_key` and `access_token_secret` for OAuth 1.1. It will also
  include an `auth_entity` query parameter with the string key of an
  [auth entity](#auth-entities) that has more data (and functionality) for the
  authenticated user. If the user declined the OAuth authorization request, the
  only query parameter besides `state` will be `declined=true`.

- `finish(auth_entity, state=None)` is run in the initial callback request after
  the OAuth response has been processed. `auth_entity` is the newly created auth
  entity for this connection, or `None` if the user declined the OAuth
  authorization request.

  By default, `finish` redirects to the path you specified in `to()`, but you
  can subclass `CallbackHandler` and override it to run your own code inside the
  OAuth callback instead of redirecting:

```python
class MyCallbackHandler(facebook.CallbackHandler):
  def finish(self, auth_entity, state=None):
    self.response.write('Hi %s, thanks for connecting your %s account.' %
        (auth_entity.user_display_name(), auth_entity.site_name()))
```

  However, this is *not* currently supported for Google+ and Blogger. Hopefully
  that will be fixed in the future.

### Auth entities

Each site defines an App Engine datastore
[ndb.Model class](https://developers.google.com/appengine/docs/python/datastore/entities#Python_Kinds_and_identifiers)
that stores each user's OAuth credentials and other useful information, like
their name and profile URL. The class name is of the form <em>Site</em>Auth, e.g.
FacebookAuth. Here are the useful methods:

- `site_name()` returns the human-readable string name of the site, e.g.
  "Facebook".

- `user_display_name()` returns a human-readable string name for the user, e.g.
  "Ryan Barrett". This is usually their first name, full name, or username.

- `access_token()` returns the OAuth access token. For OAuth 2 sites, this is a
  single string. For OAuth 1.1 sites (currently just Twitter, Tumblr, and Flickr),
  this is a (string key, string secret) tuple.

The following methods are optional. Auth entity classes usually implement at
least one of them, but not all.

- `api()` returns a site-specific API object. This is usually a third party
  library dedicated to the site, e.g. [Tweepy](https://github.com/tweepy/tweepy)
  or [python-instagram](https://github.com/Instagram/python-instagram). See the
  site class's docstring for details.

- `urlopen(data=None, timeout=None)` wraps `urllib2.urlopen()` and adds the
  OAuth credentials to the request. Use this for making direct HTTP request to a
  site's REST API.

- `http()` returns an `httplib2.Http` instance that adds the OAuth credentials
  to requests.


Development
---
Most dependencies are clean, but we've made patches to some that we haven't
(yet) tried to push upstream. If we ever switch submodule repos for those
dependencies, make sure the patches are included!

* [snarfed/gdata-python-client@fabb622](https://github.com/snarfed/gdata-python-client/commit/fabb6227361612ac4fcb8bef4438719cb00eaa2b)
* [snarfed/gdata-python-client@8453e33](https://github.com/snarfed/gdata-python-client/commit/8453e3388d152ac650e22d219fae36da56d9a85d)

To convert README.md to README.rst:

`pandoc --from=markdown --to=rst --output=README.rst README.md`

TODO:

* Google+ and Blogger need some love:
  * handle declines
  * allow overriding `CallbackHandler.finish()`
  * support `StartHandler.redirect_url()`
  * allow more than one `CallbackHandler` per app
* clean up app key/secret file handling. (standardize file names? put them in a subdir?)
* implement CSRF protection for all sites
* implement [Blogger's v3 API](https://developers.google.com/blogger/docs/3.0/getting_started)
