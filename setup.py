"""setuptools setup module for oauth-dropins.

Docs:
https://packaging.python.org/en/latest/distributing.html
http://pythonhosted.org/setuptools/setuptools.html

Based on https://github.com/pypa/sampleproject/blob/master/setup.py
"""
from setuptools import setup, find_packages


setup(name='oauth-dropins',
      version='3.0',
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
          'Topic :: Software Development :: Libraries :: Python Modules',
          'Environment :: Web Environment',
          'License :: OSI Approved :: MIT License',
          'License :: Public Domain',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.3',
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
      ],
      keywords='oauth appengine',
      install_requires=[
          'beautifulsoup4~=4.8',
          'cachetools~=3.1',
          'gdata-python3~=3.0',
          'google-cloud-ndb~=1.1',
          'humanize~=0.5',
          'jinja2~=2.10',
          'mf2py~=1.1,>=1.1.2',
          'mf2util>=0.5.0',
          'oauthlib~=3.1',
          'python-tumblpy~=1.1',
          'requests-oauthlib',
          'requests~=2.22',
          'tweepy~=3.7',
          'ujson~=1.35',
          'urllib3~=1.14',
          'webapp2>=3.0.0b1',
      ],
      tests_require=['mox3~=0.28'],
)
