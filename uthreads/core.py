import os
import sys
import time
import heapq
import types
import select
import traceback
import threading

if __debug__: import weakref

from twisted.internet import defer, reactor
from twisted.python import failure, log

__all__ = [
    'uSleepQueue', 'uThread',
    'current_thread',
    'spawn', 'sleep',
    'run',
    'returns_deferred', 'uthreaded'
    ]

COOP_ITERS = 10

class uSleepQueue(object):
    """ A queue of deferreds which are waiting (without being
    scheduled) for some event.  Instances of this class are specially
    recognized by this module, so all operations which might block
    a uthread should yield an instance of this class or a subclass.

    This class can be used by other libraries implementing
    complex blocking operations, such as a microthreaded socket
    implementation.  It is generally not used directly by
    microthreaded applications.

    In a Twisted context, this represents a list of deferreds, some or all
    of which will be fired when the event takes place.
    """
    __slots__ = [ 'deferreds' ]
    def __init__(self):
        self.deferreds = []

    def add(self):
        """
        Add a new thread waiting on this queue; returns a deferred.
        """
        d = defer.Deferred()
        self.deferreds.append(d)
        return d

    def nwaiting(self):
        """
        Return the number of threads waiting on this queue; since microthreading
        involves cooperative yields, we can save extra scheduling cycles if a queue
        is empty.
        """
        return len(self.deferreds)

    def throw(self, exc_info):
        """
        Throw exc_info to *all* waiting threads.
        """
        for d in self.deferreds:
            d.errback(failure.Failure(exc_info))
        self.deferreds = []

    def throwone(self, exc_info):
        """
        Throw exc_info to *one* waiting thread.
        """
        if self.deferreds:
            d = self.deferreds.pop(0)
            d.errback(failure.Failure(exc_info))

    def wake(self, result):
        """
        Wake *all* waiting threads with result.  If result is mutable, and the
        awakened threads modify it, behavior is unspecified.
        """
        for d in self.deferreds: 
            d.callback(result)
        self.deferreds = []

    def wakeone(self, result):
        """
        Wake *one* waiting thread with result.
        """
        if self.deferreds:
            d = self.deferreds.pop(0)
            d.callback(result)

class uThread(object):
    __slots__ = [ 'target', 'name', 'args', 'kwargs',
                  '_state',
                  '_stack',
                  '_stepfn', '_stepargs',
                  '_result', '_join_sleepq', '_sleep_sleepq' ]
    CREATED, RUNNING, FINISHED = range(3)
    def __init__(self, target=None, name='unnamed', args=(), kwargs={}):
        self.target = target
        self.name = name
        self.args = args
        self.kwargs = kwargs

        self._state = self.CREATED

        self._stack = None

        self._stepfn = None
        self._stepargs = None

        self._join_sleepq = None
        self._sleep_sleepq = None

    # support for the @uthreaded decorator's debugging data
    if __debug__:
        last_uthreaded_return = None

    def __repr__(self):
        return "<%s %r at 0x%x>" % (self.__class__.__name__, self.name, id(self))

    def run(self):
        """
        The generator performing the work of the thread.  This function can be overridden
        by subclasses, if desired.  It may:
          - yield a generator with this behavior to begin executing that generator;
            any return value from that generator will be returned as the value of the
            yield expression.
          - raise an exception
            - if that exception is StopIteration, and its arguments are not empty, then
              the argument is taken as the "return value" of the function
          - yield a uSleepQueue to sleep on that queue
          - yield a Deferred to sleep until it is fired; callbacks will return the value
            of the deferred, while errbacks will throw the exception embedded in a Failure
            object, or the Failure itself if no exception is embedded.  Callbacks with
            multiple values are not allowed (this may change).
          - yield any other value (including None) to receive that value back at the
            next scheduling interval.
        """
        raise StopIteration((yield self.target(*self.args, **self.kwargs)))

    def getName(self):
        """
        Get the name of this uThread
        """
        return self.name

    def setName(self, name):
        """
        Set the name of this uThread
        """
        self.name = name

    def isAlive(self):
        """
        Return a true value if this uThread has been started and has not finished.
        """
        return self._state == self.RUNNING

    def join(self):
        """
        Return a uSleepQueue that will fire when this uThread
        finishes, or the result of the thread if it has already
        finished.  Generally used like this::
          # wait until worker has finished
          yield worker.join()
        """
        if self._state == self.FINISHED: 
            if self._result[0]:
                return self._result[1]
            else:
                raise self._result[1][0], self._result[1][1], self._result[1][2]

        # invent a _join_sleepq if necessary
        if not self._join_sleepq:
            self._join_sleepq = uSleepQueue()

        # and return it; the calling thread will yield it and consequently
        # sleep on it
        return self._join_sleepq

    def start(self):
        """
        Begin executing the uThread.  It may or may not begin
        execution immediately.
        """
        assert self._state == self.CREATED

        self._state = self.RUNNING

        topgen = self._toplevel()
        self._stack = [ topgen ]
        self._stepfn = topgen.next
        self._stepargs = ()

        self._step()

    # TODO: remove
    def _toplevel(self):
        try:
            self._result = (True, (yield self.run()))
        except:
            # TODO: trim traceback down to here
            self._state = self.FINISHED
            self._result = (False, sys.exc_info())
            if self._join_sleepq:
                self._join_sleepq.throw(failure.Failure())
            else:
                log.msg("Possible uncaught exception in uThread: %r" % (self._result[1][1],))
                # TODO: handle this when the uThread is GC'd?
        else:
            self._state = self.FINISHED
            if self._join_sleepq:
                self._join_sleepq.wake(self._result[1])

    def _step(self):
        global _current_thread
        iterations = 0
        while True:
            iterations += 1
            _current_thread = self
            sleep_d = None
            try:
                stepresult = self._stepfn(*self._stepargs)

            except StopIteration, e:
                # generator is done
                if len(self._stack) > 1:
                    self._stack.pop()
                    self._stepfn = self._stack[-1].send
                    if e.args: # if a return value was included, pass it up
                        self._stepargs = (e.args[0],)
                    else:
                        self._stepargs = (None,)
                else:
                    # _toplevel is done, so we're finished
                    self._stack[-1].close() # finish off the _toplevel() generator
                    break

            except GeneratorExit:
                # generator exited early
                assert len(self._stack) > 1, "_toplevel() threw GeneratorExit"
                self._stack.pop()
                self._stepfn = self._stack[-1].next
                self._stepargs = ()

            except:
                # generator raised an exception
                assert len(self._stack) > 1, "_toplevel raised an exception: %s" % (sys.exc_info(),)
                self._stack.pop()
                self._stepfn = self._stack[-1].throw

                # drop the traceback element for this frame (users don't want to see this mess)
                cl, ex, tb = sys.exc_info()
                tb = tb.tb_next
                self._stepargs = (cl, ex, tb)
            else:
                if __debug__:
                    uThread._generator_seen(stepresult)
                if type(stepresult) is types.GeneratorType:
                    # starting a nested generator
                    self._stack.append(stepresult)
                    self._stepfn = self._stack[-1].next
                    self._stepargs = ()
                
                elif isinstance(stepresult, uSleepQueue):
                    # sleep on a sleep queue
                    sleep_d = stepresult.add()

                elif isinstance(stepresult, defer.Deferred):
                    # sleep on a Deferred
                    sleep_d = stepresult

                else:
                    # if it's time for this thread to yield up the CPU, do so
                    if not sleep_d and iterations > COOP_ITERS:
                        sleep_d = defer.Deferred()
                        reactor.callLater(0, sleep_d.callback, stepresult)
                    else:
                        # bounce any other yielded result back to the generator
                        self._stepfn = self._stack[-1].send
                        self._stepargs = (stepresult,)
                
            # if we're sleeping, set up the deferred and break
            if sleep_d:
                def nextstep_cb(res):
                    self._stepfn = self._stack[-1].send
                    self._stepargs = (res,)
                    self._step()
                def nextstep_eb(f):
                    if isinstance(f, failure.Failure):
                        # getting the traceback object is a bit tricky in Twisted
                        if hasattr(f, 'getTracebackObject'):
                            tb = f.getTracebackObject()
                        elif hasattr(f, 'tb'):
                            tb = f.tb
                        else:
                            tb = None
                        # Twisted has a tendency to call "cleanFailure" too much; this
                        # throws out the original Python traceback and substitutes a
                        # "fake" traceback, which won't fool throw().  Such is life with
                        # Twisted.
                        if tb is not None and not isinstance(tb, types.TracebackType):
                            tb = None
                        exc_info = (f.type, f.value, tb)
                    else:
                        exc_info = (type(f), f, None) # TODO: is this right? can it happen?
                    self._stepfn = self._stack[-1].throw
                    self._stepargs = exc_info
                    self._step()
                sleep_d.addCallbacks(nextstep_cb, nextstep_eb)
                break

    if __debug__:
        @staticmethod
        def _generator_seen(yielded):
            """Utility function to check that no generators have been missed"""
            if uThread.last_uthreaded_return is None: return
            last_obj_ref, last_fn = uThread.last_uthreaded_return
            if last_obj_ref() is yielded:
                uThread.last_uthreaded_return = None # we got the object we were supposed to get
            else:
                # must have missed this object somehow
                raise RuntimeError("%r, result of %r, was not yielded to the scheduler"
                                  % (last_obj_ref(), last_fn))

global _current_thread
def current_thread():
    return _current_thread

def spawn(generator):
    """
    Spawn a new, started thread with the given generator.
    This is most often called like this::
      worker_thread = uthreads.spawn(worker(datum1, datum2))
    """
    # make sure uThread "sees" GENERATOR, lest it think someone forgot
    # to yield it
    if __debug__:
        uThread._generator_seen(generator)

    thd = uThread(target=lambda : generator)
    thd.start()
    return thd

def sleep(timeout):
    """
    Sleep for TIMEOUT seconds
    """
    d = defer.Deferred()
    reactor.callLater(timeout, d.callback, None)
    return d

def run(callable, *args, **kwargs):
    """
    Start a new uthread, returning a deferred that will callback when it
    completes, or errback with any failure.
    """
    thd = uThread(target=callable, args=args, kwargs=kwargs, name="main")

    # we "join" the thread before starting it, and return the resulting deferred.
    q = thd.join()
    d = q.add()

    thd.start()

    return d

## decorators

def returns_deferred(fn):
    """
    A decorator which makes the underlying microthreaded function return a
    Deferred.  Used to interface microthreaded functions to Twisted.  Usage::
        @returns_deferred
        def my_uthreaded_fn(remote, x, y):
            # use microthreaded style inside the function
            yield remote.set_x(x)
            yield remote.set_y(y)
            raise StopIteration(x+y)

        def call_fn(remote):
            # treat it as a function returning a deferred
            d = my_uthreaded_fn(remote, 10, 20)
            def print_result(res):
                print "result: res"
            d.addCallback(print_result)
    """
    def wrapper(*args, **kwargs):
        return run(fn, *args, **kwargs)
    wrapper.func_name = fn.func_name
    return wrapper

def uthreaded(fn):
    """
    A decorator to signal that the decorated function is microthreaded, and
    should be called within a C{yield} expression.  If __debug__ is False, this
    doesn't do much of anything.  Otherwise, when the function is called, it
    checks that it does, indeed, return a generator, and that the generator
    makes it back to the uthread scheduler, helping to avoid errors where
    microthreaded functions are accidentally called without C{yield}.
    """
    if not __debug__: return fn
    def wrapper(*args, **kwargs):
        obj = fn(*args, **kwargs)

        # if the function is not actually uThreaded, then there's nothing to worry
        # about.  The object is probably referenced from other places, so our weakref
        # trick is unlikely to work.
        if not isinstance(obj, types.GeneratorType):
            return obj

        # if the last object returned from a @uthreaded function has not yet been
        # seen (and set to None) by the scheduler, then we have a problem.
        if uThread.last_uthreaded_return is not None:
            last_obj_ref, last_fn = uThread.last_uthreaded_return
            raise RuntimeError("%r, result of %r, was not yielded to the scheduler"
                              % (last_obj_ref(), last_fn))

        # add a weakref to this object; if the calling function immediately discards it,
        # which is the most common error, then this callback will detect the error.
        def early_unref(ref):
            raise TypeError("generator from %r was not yielded to the scheduler" % fn)
        obj_ref = weakref.ref(obj, callback=early_unref)
        uThread.last_uthreaded_return = (obj_ref, fn)
        return obj

    wrapper.func_name = fn.func_name
    wrapper.func_doc = fn.func_doc
    return wrapper
