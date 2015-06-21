# Add the App Engine SDK's bundled libraries (django, mox, webob, yaml, etc.) to
# sys.path so we can use them instead of adding them all to tests_require in
# setup.py.
# https://cloud.google.com/appengine/docs/python/tools/localunittesting#Python_Setting_up_a_testing_framework
import dev_appserver
dev_appserver.fix_sys_path()

# Suppress logging by default.
import logging, sys
if '--debug' in sys.argv:
  sys.argv.remove('--debug')
  logging.getLogger().setLevel(logging.DEBUG)
else:
  logging.disable(logging.CRITICAL + 1)

# Monkey patch to fix template loader issue:
#
# File "/usr/local/google_appengine/lib/django-1.4/django/template/loader.py", line 101, in find_template_loader:
# ImproperlyConfigured: Error importing template source loader django.template.loaders.filesystem.load_template_source: "'module' object has no attribute 'load_template_source'"
from django.template.loaders import filesystem
filesystem.load_template_source = filesystem._loader.load_template_source
