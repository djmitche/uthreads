import os
import sys
from Queue import Empty, Full
from collections import deque

from uthread import *

__all__ = [
    'Lock',
    'Queue', 'Empty', 'Full',
    ]

class Lock(uSleepQueue):
    """
    A lock can be acquired by only one thread at any time, just like a threading-based
    Lock.  Note that in microthreaded programming, locks are only needed if a critical
    section spans a "yield", which should rarely happen.
    """
    __slots__ = [ 'held' ]
    def __init__(self):
        uSleepQueue.__init__(self)
        self.held = False

    def acquire(self):
        while self.held:
            yield self
        self.held = True

    def release(self):
        assert self.held, "Attempt to release() a lock that's not held"
        self.held = False
        # this assumes awakened thread will immediately acquire the lock,
        # and will potentially deadlock if this is violated
        self.wakeone(None)

class Queue(object):
    __slots__ = [ 'max_size', '_data', '_sleepq', '_sleeping_on' ]
    def __init__(self, max_size=None):
        assert max_size is None or max_size > 0
        self.max_size = max_size
        self._data = deque()
        self._sleepq = uSleepQueue()

    def empty(self):
        return not self._data

    def full(self):
        return self.max_size is not None and len(self._data) >= self.max_size

    def _pop(self):
        v = self._data.popleft()
        self._sleepq.wakeone(None)
        return v

    def _push(self, v):
        self._data.append(v)
        self._sleepq.wakeone(None)
        return v

    def get(self):
        while True:
            if self._data:
                raise StopIteration(self._pop())
            yield self._sleepq

    def get_nowait(self):
        if self._data:
            raise StopIteration(self._pop())
        raise Empty

    def put(self, v):
        while True:
            if self.max_size is None or len(self._data) < self.max_size:
                self._push(v)
                return
            yield self._sleepq

    def put_nowait(self, v):
        if self.max_size is None or len(self._data) < self.max_size:
            self._push(v)
            return
        raise Full

    def qsize(self):
        return len(self._data)
