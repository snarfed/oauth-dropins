"""setuptools setup module for oauth-dropins.

Docs: https://setuptools.pypa.io/en/latest/userguide/

Based on https://github.com/pypa/sampleproject/blob/master/setup.py
"""
from setuptools import setup, find_packages


setup(name='oauth-dropins',
      version='6.2',
      description='Drop-in OAuth Flask views for many popular sites.',
      long_description=open('README.md').read(),
      long_description_content_type='text/markdown',
      url='https://github.com/snarfed/oauth-dropins',
      packages=find_packages(),
      include_package_data = True,
      author='Ryan Barrett',
      author_email='oauth-dropins@ryanb.org',
      license='Public domain',
      python_requires='>=3.7',
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Intended Audience :: Developers',
          'Topic :: System :: Systems Administration :: Authentication/Directory',
          'Topic :: Software Development :: Libraries :: Python Modules',
          'Environment :: Web Environment',
          'License :: OSI Approved :: MIT License',
          'License :: Public Domain',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
          'Programming Language :: Python :: 3.9',
      ],
      keywords='oauth appengine',
      install_requires=[
          'atproto>=0.0.23',
          'beautifulsoup4>=4.8',
          'cachetools>=3.1',
          'domain2idna>=1.12',
          'flask>=2.0.1',
          'flask-caching>=1.10.1',
          'gdata-python3>=3.0',
          'google-cloud-ndb>=1.10.1',
          'humanize>=3.1.0',
          'jinja2>=2.10',
          'mf2py>=1.1',
          'mf2util>=0.5.0',
          'oauthlib>=3.1',
          'pkce>=1.0.3',
          'praw>=7.3.0',
          'python-tumblpy>=1.1',
          'requests-oauthlib',
          'requests>=2.22',
          'tweepy>=4.5',
          'ujson>=5.1',
          'urllib3>=1.14',
      ],
      tests_require=['mox3>=0.28,<2.0'],
      extras_require={
          'docs': [
              'sphinx',
              'sphinx-rtd-theme',
          ],
      },
)
