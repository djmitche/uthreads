#!/usr/bin/env python

from setuptools import setup
import sys

from ez_setup import use_setuptools
use_setuptools()

if sys.version_info < (2, 5):
  print "Python 2.5 or higher is required."
  sys.exit(1)

classifiers = [
    "Framework :: Twisted",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: GNU General Public License (GPL)",
    "Programming Language :: Python",
    "Topic :: Software Development :: Libraries :: Python Modules",
    'Development Status :: 4 - Beta',
]
setup(name='uthreads',
      version='1.0',
      author='Dustin J. Mitchell',
      author_email='dustin@v.igoro.us',
      description='Python Microthreading Library',
      long_description=open("README.txt").read(),
      url='http://code.google.com/p/uthreads',
      classifiers=classifiers,
      license="GPLv2",

      packages=['uthreads'],
      include_package_data = True,
      zip_safe=True,

      test_suite="test",

      install_requires=['Twisted'],
)
