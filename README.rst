.. image:: https://raw.github.com/snarfed/oauth-dropins/master/oauth_dropins/static/oauth_shiny_128.png
   :target: https://github.com/snarfed/oauth-dropins
.. image:: https://circleci.com/gh/snarfed/oauth-dropins.svg?style=svg
   :target: https://circleci.com/gh/snarfed/oauth-dropins
.. image:: https://coveralls.io/repos/github/snarfed/oauth-dropins/badge.svg?branch=master
   :target: https://coveralls.io/github/snarfed/oauth-dropins?branch=master

This is a collection of drop-in
`Google App Engine <https://appengine.google.com/>`__ request handlers for the
initial
`OAuth <http://oauth.net/>`__ client flows for many popular sites, including
Blogger, Dropbox, Facebook, Flickr, Google+, IndieAuth, Instagram, Twitter,
Tumblr, and WordPress.com.

Check out the demo app! https://oauth-dropins.appspot.com/


Quick start
===========

Here's a full example of using the Facebook drop-in.

1. `Install oauth-dropins into your App Engine app. <https://github.com/snarfed/oauth-dropins#quick-start>`__

1. Put your `Facebook
   application <https://developers.facebook.com/apps>`__'s ID and secret
   in two plain text files in your app's root directory,
   ``facebook_app_id`` and ``facebook_app_secret``. (If you use git,
   you'll probably also want to add them to your ``.gitignore``.)

1. Create a ``facebook_oauth.py`` file with these contents:

.. code:: python

    from oauth_dropins import facebook
    import webapp2

    application = webapp2.WSGIApplication([
      ('/facebook/start_oauth', facebook.StartHandler.to('/facebook/oauth_callback')),
      ('/facebook/oauth_callback', facebook.CallbackHandler.to('/next'))]

1. Add these lines to ``app.yaml``:

.. code:: yaml

    - url: /facebook/(start_oauth|oauth_callback)
      script: facebook_oauth.application
      secure: always

Voila! Send your users to ``/facebook/start_oauth`` when you want them
to connect their Facebook account to your app, and when they're done,
they'll be redirected to ``/next?access_token=...`` in your app.

All of the sites provide the same API. To use a different one, just
import the site module you want and follow the same steps. The filenames
for app keys and secrets also differ by site;
`appengine_config.py <https://github.com/snarfed/oauth-dropins/blob/master/oauth_dropins/appengine_config.py>`__
has the full list.


