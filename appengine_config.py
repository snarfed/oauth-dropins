# Load packages from virtualenv
# https://cloud.google.com/appengine/docs/python/tools/libraries27#vendoring
from google.appengine.ext import vendor
vendor.add('local')

from oauth_dropins.appengine_config import *
