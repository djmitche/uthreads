from __future__ import absolute_import

import os
import sys
import time
import heapq
import types
import errno
import select
import string
import traceback
import socket as socketmodule

from uthread import *

__all__ = [
    "socket"
    ]

# reflect all CONSTANTS from stdlib socket module into
# our global namespace
g = globals()
for sym in dir(socketmodule):
    if sym[0] in string.uppercase:
        g[sym] = socketmodule.__dict__[sym]
        __all__.append(sym)
del g

error = socketmodule.error

# TODO: 
# - timeouts on sockets
# - wrap ssl

class socket(object):
    """
    A subclass of the standard L{socket.socket} which replaces all blocking
    functions with uthread-compliant generators otherwise posessing the same
    semantics.

    @note: this class is based closely on L{asyncore.dispatcher}, by Sam 
    Rushing.

    @note: while accessing the same socket from multiple uthreads is
    supported (for example, several uthreads can call accept()
    simultaneously), non-sensical behavior (such as calling recv() on a
    listening socket) will produce unpredicatably non-sensical results.
    """

    # The general structure of each of the potentially blocking functions
    # is this: try to perform the action. if the operation would block, 
    # sleep on the appropriate (read or write) uSleepQueue.  On waking, try
    # to perform the action again, and re-sleep if the operation would 
    # block again.

    def __init__(self, *args, **kwargs):
        self._s = socketmodule.socket(*args, **kwargs)
        self._s.setblocking(0)

        self._readq = uSleepQueue()
        self._writeq = uSleepQueue()

    # TODO: add timeout support here (set two callbacks on the sleepq, have each one cancel
    # the other; will require reg/unreg with uMonitor)
    def _sleep_on_read(self):
        current_scheduler().monitor.callback_on_read(self._s.fileno(), self._readq.wakeone, True)
        return self._readq

    def _sleep_on_write(self):
        current_scheduler().monitor.callback_on_write(self._s.fileno(), self._writeq.wakeone, True)
        return self._writeq

    def accept(self):
        while True:
            try:
                conn, addr = self._s.accept(self)
            except error, why:
                if why[0] != errno.EWOULDBLOCK: raise
            else:
                break

            yield self._sleep_on_read()
        raise StopIteration((conn, addr))

    def connect(self, addr):
        while True:
            try:
                self._s.connect_ex(addr)
            except error, why:
                if why[0] == errno.EISCONN: break
                if why[0] not in (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK):
                    raise
            else:
                break

            yield self._sleep_on_read()

    def recv(self, buflen, flags=0):
        while True:
            try:
                raise StopIteration(self._s.recv(buflen, flags))
            except error, why:
                if why[0] in (errno.ECONNRESET, errno.ENOTCONN, errno.ESHUTDOWN):
                     raise StopIteration('') # signal that remote socket is closed
                if why[0] != errno.EWOULDBLOCK:
                    raise

            yield self._sleep_on_read()

    def recvfrom(buflen, flags=0):
        raise NotImplemented # TODO

    def sendall(self, data, flags=0):
        while data:
            sent = yield self.send(data, flags)
            data = data[sent:]

    def send(self, data, flags=0):
        while True:
            try:
                raise StopIteration(self._s.send(data, flags))
            except error, why:
                if why[0] != errno.EWOULDBLOCK: raise

            yield self._sleep_on_write()

    def sendto(self, data, second, third):
        raise NotImplemented # TODO

    def setblocking(self, blocking):
        assert not blocking, "attempt to set a ulib.socket.socket object to blocking operation"

    # any other attributes are passed straight along to the socket object
    def __getattr__(self, k):
        v = getattr(self._s, k)
        self.__dict__[k] = v
        return v
