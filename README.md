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
* parameterize OAuth scopes (only applicable to some sites)
* clean up app key/secret file handling. (standardize file names? put them in a
  subdir?)
* implement CSRF protection for all sites
* implement Blogger's v3 API:
  https://developers.google.com/blogger/docs/3.0/getting_started
