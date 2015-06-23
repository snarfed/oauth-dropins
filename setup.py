"""setuptools setup module for oauth-dropins.

Docs:
https://packaging.python.org/en/latest/distributing.html
http://pythonhosted.org/setuptools/setuptools.html

Based on https://github.com/pypa/sampleproject/blob/master/setup.py
"""
from setuptools import setup, find_packages

# test/__init__.py makes App Engine SDK's bundled libraries importable.
import oauth_dropins.test

setup(name='oauth-dropins',
      version='1.0',
      description='Drop-in App Engine OAuth client handlers for many popular sites.',
      long_description=open('README.rst').read(),
      url='https://github.com/snarfed/oauth-dropins',
      packages=find_packages(),
      author='Ryan Barrett',
      author_email='oauth-dropins@ryanb.org',
      license='Public domain',
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Intended Audience :: Developers',
          'Topic :: System :: Systems Administration :: Authentication/Directory',
          'Environment :: Web Environment',
          'License :: OSI Approved :: MIT License',
          'License :: Public Domain',
          'Programming Language :: Python :: 2',
      ],
      keywords='oauth appengine',
      # Keep in sync with requirements.txt!
      install_requires=[
          'gdata>=2.0.18',
          'google-api-python-client>=1.4.0',
          'httplib2',
          'mox',
          'oauth2client',
          'oauthlib',
          'python-tumblpy',
          'requests<2.6.0',
          'requests-oauthlib',
          'tweepy',
      ],
      test_suite='oauth_dropins',
)
