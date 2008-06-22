#!/usr/bin/env python

from distutils.core import setup
import sys

if sys.version_info < (2, 5):
  print "Python 2.5 or higher is required."
  sys.exit(1)

setup(name='uthread',
      version='1.0a3',
      author='Dustin J. Mitchell',
      author_email='dustin@cs.uchicago.edu',
      description='Python Microthreading Library',
      url='http://code.google.com/p/uthreads',
      packages=['uthreads'])
