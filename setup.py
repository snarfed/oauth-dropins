"""setuptools setup module for oauth-dropins.

Docs: https://packaging.python.org/en/latest/distributing.html

Based on https://github.com/pypa/sampleproject/blob/master/setup.py
"""
from setuptools import setup

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
      # List run-time dependencies here.  These will be installed by pip when
      # your project is installed. For an analysis of "install_requires" vs pip's
      # requirements files see:
      # https://packaging.python.org/en/latest/requirements.html
      install_requires=[
          'google-api-python-client',
          'httplib2',
          'oauthlib',
          'python-tumblpy',
          'requests',
          'requests-oauthlib',
          'tweepy',
      ],
)
