# Load packages from virtualenv
# https://cloud.google.com/appengine/docs/python/tools/libraries27#vendoring
from google.appengine.ext import vendor
vendor.add('local')

from oauth_dropins.appengine_config import *

# Make requests and urllib3 play nice with App Engine.
# https://github.com/snarfed/bridgy/issues/396
# http://stackoverflow.com/questions/34574740
from requests_toolbelt.adapters import appengine
appengine.monkeypatch()

# Suppress warnings. These are duplicated in granary and bridgy; keep them in sync!
import warnings
warnings.filterwarnings('ignore', module='bs4',
                        message='No parser was explicitly specified')
warnings.filterwarnings('ignore', message='urllib3 is using URLFetch')
