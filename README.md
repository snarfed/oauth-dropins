oauth-dropins
=============

_Still in progress! Should be ready in a week or two._

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

This software is released into the public domain. See LICENSE for details.


Development
---
TODO:
* drop google-api-python-client because it requires you to log into your google
  account to store credentials and intermediate data.
* parameterize OAuth scopes
* switch BloggerAuth key name to a unique id (blog id?)
