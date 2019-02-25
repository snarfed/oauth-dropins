"""setuptools setup module for oauth-dropins.

Docs:
https://packaging.python.org/en/latest/distributing.html
http://pythonhosted.org/setuptools/setuptools.html

Based on https://github.com/pypa/sampleproject/blob/master/setup.py
"""
from setuptools import setup, find_packages
from setuptools.command.test import ScanningLoader


class TestLoader(ScanningLoader):
  def __init__(self, *args, **kwargs):
    super(ScanningLoader, self).__init__(*args, **kwargs)
    # webutil/tests/__init__.py makes App Engine SDK's bundled libraries importable.
    import oauth_dropins.webutil.tests


setup(name='oauth-dropins',
      version='2.0',
      description='Drop-in App Engine OAuth client handlers for many popular sites.',
      long_description=open('README.md').read(),
      long_description_content_type='text/markdown',
      url='https://github.com/snarfed/oauth-dropins',
      packages=find_packages(),
      include_package_data = True,
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
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.3',
      ],
      keywords='oauth appengine',
      # Keep in sync with requirements.txt!
      install_requires=[
          'future>=0.16.0',
          'gdata>=2.0.18',
          'google-api-python-client>=1.7.4',
          'httplib2',
          'humanize',
          'oauth2client>=4.1.1',
          'oauthlib',
          'python-tumblpy',
          'requests>=2.10.0',
          'requests-oauthlib',
          'requests-toolbelt>=0.6.2',
          'tweepy>=3.0',
          'beautifulsoup4',
          'mf2py>=1.1.2',
          'mf2util',
          'urllib3>=1.14',
      ],
      extras_require={
          'appenginesdk': ['appengine-sdk >= 1.9.40.post0'],
      },
      test_loader='setup:TestLoader',
      test_suite='oauth_dropins.webutil',
)
