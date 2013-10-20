![OAuth logo](https://raw.github.com/snarfed/oauth-dropins/master/static/oauth_logo_shiny_128.png)

oauth-dropins
=============

About
---

A collection of drop-in [Google App Engine](https://appengine.google.com/)
request handlers for the initial [OAuth](http://oauth.net/) client flows for
many popular sites:

* Blogger (v2)
* Dropbox
* Facebook
* Google+
* Instagram
* Twitter (v1.1)
* Tumblr
* Wordpress.com (and Jetpack REST API)

This repo also provides an example demo app:
http://oauth-dropins.appspot.com/.

This software is released into the public domain. See LICENSE for details.


Quick start
---

Here's a full example of integrating the Facebook drop-in with an app running
inside dev_appserver on localhost. First, clone or download this repo, then
initialize its git submodules with `git submodule init && git submodule update`.
(All dependencies are included as submodules.)

Next,
[register a new Facebook application](https://developers.facebook.com/apps),
enter `localhost` as the App Domain, choose Website with Facebook Login, and
enter `http://localhost:8080/` as the Site URL. Once it's created put its app ID
and secret in two new plain text files in your app's root directory,
`facebook_app_id` and `facebook_app_secret`.

Choose two new URL paths that your app will use for starting and finishing the
Facebook OAuth flow, e.g. `/facebook/start_oauth` and
`/facebook/oauth_callback`. Add these lines to `app.yaml`:

```
- url: /facebook/(start_oauth|oauth_callback)
  script: facebook_oauth.application
  secure: always
```

And add this as `facebook_oauth.py`:

```
from oauth_dropins import facebook, twitter
import webapp2

application = webapp2.WSGIApplication([
  ('/facebook/start_oauth', facebook.StartHandler.to('/facebook/oauth_callback')),
  ('/facebook/oauth_callback', facebook.CallbackHandler.to('/next'))]
```

Voila! Send your users to `/facebook/start_oauth` when you want them to connect
their Facebook account to your app, and when they're done, they'll be redirected
to your `/next` handler.


Usage details
---

Each site module provides `StartHandler` and `CallbackHandler` classes that
provide the `to()` methods used above.

The request handlers are full [WSGI](http://wsgi.org/) applications and may be
used in any Python web framework that supports WSGI
([PEP 333](http://www.python.org/dev/peps/pep-0333/)). Internally, they're
implemented with [webapp2](http://webapp-improved.appspot.com/).

If you'd rather handle the initial OAuth redirect in your own request handler,
you can use the return value of `StartHandler.redirect_url()`, e.g.:

```
class MyHandler(webapp2.RequestHandler):
  def get(self):
    ...
    start_handler = facebook.StartHandler.to('/facebook/oauth_callback')
    self.redirect(start_handler.redirect_url())
```

Likewise, you can run your own code in the OAuth callback by subclassing
`CallbackHandler` and implementing `finish()`:

```
class MyCallbackHandler(facebook.CallbackHandler):
  def finish(self, auth_entity, state=None):
    ...
```

Development
---
TODO:
* parameterize OAuth scopes (only applicable to some sites)
* clean up app key/secret file handling. (standardize file names? put them in a
  subdir?)
* implement CSRF protection for all sites
* implement Blogger's v3 API:
  https://developers.google.com/blogger/docs/3.0/getting_started
