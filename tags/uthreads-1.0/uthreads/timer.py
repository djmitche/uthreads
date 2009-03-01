from __future__ import absolute_import

import os
import sys
import time
import types

from twisted.internet import defer, reactor

from .core import uThread, spawn

__all__ = [
    'Timer',
    ]

class Timer(object):
    """
    Schedule a microthreaded function to be called at some future time,
    in a new microthread.  Timers can be cancelled at any time before they
    have fired.

    @ivar delayedcall: a delayed call object, if running; otherwise None
    @type delayedcall: L{twisted.internet.interfaces.IDelayedCall}

    @ivar generator: the generator supplied to the set function
    """
    __slots__ = [ 'delayedcall', 'generator' ]
    def __init__(self):
        self.delayedcall = None

    def set(self, delay, generator):
        if __debug__:
            uThread._generator_seen(generator)
        if type(generator) is not types.GeneratorType:
            raise RuntimeError("%r is not a generator (perhaps you used a regular function?)" % (generator,))
        if self.delayedcall: self.clear()

        self.generator = generator
        self.delayedcall = reactor.callLater(delay, self.fire)

    def fire(self):
        spawn(self.generator)
        self.delayedcall = None

    def clear(self):
        if not self.delayedcall: return
        self.delayedcall.cancel()
        self.delayedcall = None
