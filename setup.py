"""setuptools setup module for oauth-dropins.

Docs:
https://packaging.python.org/en/latest/distributing.html
http://pythonhosted.org/setuptools/setuptools.html

Based on https://github.com/pypa/sampleproject/blob/master/setup.py
"""
import unittest

from setuptools import setup


class TestLoader(unittest.TestLoader):
    def loadTestsFromNames(self, names, _=None):
        return self.discover(names[0])


setup(name='oauth-dropins',
      version='1.0',
      description='Drop-in App Engine OAuth client handlers for many popular sites.',
      long_description=open('README.rst').read(),
      url='https://github.com/snarfed/oauth-dropins',
      packages=['oauth_dropins', 'webutil'],
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
      install_requires=[
          'google-api-python-client',
          'httplib2',
          'oauthlib',
          'python-tumblpy',
          'requests',
          'requests-oauthlib',
          'tweepy',
      ],
      test_loader='setup:TestLoader',
      test_suite='.',
)
