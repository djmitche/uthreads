import os
import sys
import time
import types

from uthreads import *

__all__ = [
    'Timer',
    ]

class Timer(object):
    """
    Schedule a microthreaded function to be called at some future time,
    in a new microthread.  Timers can be set to repeat if desired, and can
    be cancelled at any time before they have fired.
    """
    # TODO epydoc ivars
    __slots__ = [ 'running', 'generator', 'timer' ]
    def __init__(self):
        self.running = False

    def set(self, delay, generator):
        assert type(generator) is types.GeneratorType, "%r is not a generator (perhaps you used a regular function?)" % (generator,)
        if self.running: self.clear()

        self.running = True
        self.generator = generator

        self.timer = current_scheduler().monitor.callback_on_timer(time.time() + delay, self.fire)

    def fire(self):
        spawn(self.generator)
        self.running = False

    def clear(self):
        if not self.running: return
        current_scheduler().monitor.cancel_sleep_callback(self.timer)
