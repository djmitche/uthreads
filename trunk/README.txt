Introduction
============

'uthreads' is a microthreading library layered on top of Twisted
Python. It is similar to DeferredGenerator, but uses features only
present in Python 2.5 to make the microthreaded code much more
natural to read and write. See the MotivatingExample for an idea of
how uthreads can be useful.

This project aims to be a compact, efficient, and easy-to-use
microthreading platform, allowing users to concentrate on writing
their applications in a natural fashion while retaining all of
the benefits of microthreaded programming. Applications can easily
intermix twisted code with microthreaded code, as the structure of
the application dictates.

Documentation
=============

See the wiki documentation at http://uthreads.googlecode.com/, or read
the source files in the wiki/ subdirectory of the source distribution.

Authors
=======

Dustin J. Mitchell <dustin@v.igoro.us>
