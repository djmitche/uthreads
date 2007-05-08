import os
import sys
import time
import heapq
import types
import select
import traceback
import threading

__all__ = [
    'uScheduler', 'uMonitor', 'uSleepQueue', 'uThread',
    'current_scheduler', 'current_thread',
    'spawn', 'sleep',
    'run',
    ]

# TODO: simplify monitor interface, make portable?

class uScheduler(object):
    """
    A C{uScheduler} manages scheduling a collection of C{uThread}s.

    @ivar runq: runnable threads
    @type runq: list

    @ivar non_daemon_threads: number of running non-daemon threads
    (including sleeping threads).  This value is maintained by the uThread
    class.
    @type non_daemon_threads: integer

    @ivar monitor: a uMonitor class, or None if none is needed
    @type monitor: instance or None

    @ivar current_thread: currently executing thread, or None if no thread
    is running (when scheduler is running or awaiting events)
    @type current_thread: uThread instance or None
    """

    def __init__(self):
        self.runq = [ ]
        self._running = False
        self.non_daemon_threads = 0

        # TODO: make this runtime-selectable
        self.monitor = uMonitor()

    def run(self):
        """
        Begin scheduling uthread execution. Run until stopped, or until
        there are no more non-daemon threads.
        """
        self._running = True
        while self._running and self.non_daemon_threads > 0:
            # poll for new events
            self.monitor.poll(not bool(self.runq))

            # TODO: abstract this into a subclass too
            runq, self.runq = self.runq, []

            # now run the available threads in the runq, building a
            # new runq in the process
            for uthread in runq:
                self.current_thread = uthread
                uthread._step()
            self.current_thread = None

    def stop(self):
        self._running = False

    ##
    # Utility functions for uThread objects

    def queue(self, uthread):
        if uthread in self.runq: return
        self.runq.append(uthread)

class uSleepQueue(object):
    """
    A queue of uthreads which are waiting (without being scheduled) for
    some event.  Instances of this class are specially recognized by
    this module, so all operations which might block a uthread should
    yield an instance of this class or a subclass.
    """
    __slots__ = [ 'uthreads' ]
    def __init__(self):
        self.uthreads = []

    def add(self, uthread):
        self.uthreads.append(uthread)

    def throw(self, exc_info):
        for uthread in self.uthreads:
            uthread._wake_thread(exc_info=exc_info)
        self.uthreads = []

    def throwone(self, exc_info):
        if self.uthreads:
            uthread = self.uthreads.pop(0)
            uthread._wake_thread(exc_info=exc_info)

    def wake(self, result):
        for uthread in self.uthreads: 
            uthread._wake_thread(result)
        self.uthreads = []

    def wakeone(self, result):
        if self.uthreads:
            uthread = self.uthreads.pop(0)
            uthread._wake_thread(result)

class uThread(object):
    __slots__ = [ 'target', 'name', 'args', 'kwargs',
                  '_running', '_daemon',
                  '_stack',
                  '_stepfn', '_stepargs',
                  '_result', '_join_sleepq', '_sleep_sleepq' ]
    def __init__(self, target=None, name='unnamed', args=(), kwargs={}):
        self.target = target
        self.name = name
        self.args = args
        self.kwargs = kwargs

        self._running = False
        self._daemon = False

        self._stack = None

        self._stepfn = None
        self._stepargs = None

        self._result = None
        self._join_sleepq = None
        self._sleep_sleepq = None

    def __repr__(self):
        return "<%s %r at 0x%x>" % (self.__class__.__name__, self.name, id(self))

    @classmethod
    def spawn(cls, generator):
        uth = cls(target=lambda : generator)
        uth.start()
        return uth

    def run(self):
        """
        The generator performing the work of the thread.  This function may
          - yield a generator with the same behavior to begin executing that generator;
            any return value from that generator will be returned as the value of the
            yield expression.
          - raise an exception
            - if that exception is StopIteration, and its arguments are not empty, then
              the argument is taken as the "return value" of the function
          - yield any other value (including None) to receive that value back at the
            next scheduling interval.
        """
        raise StopIteration((yield self.target(*self.args, **self.kwargs)))

    def getName(self):
        return self.name

    def setName(self, name):
        self.name = name

    def isAlive(self):
        return self._running

    def isDaemon(self):
        return self._daemon

    def setDaemon(self, d):
        if d and not self._daemon and self._running:
            scheduler.non_daemon_threads -= 1
            self._daemon = True
        if not d and self._daemon and self._running:
            scheduler.non_daemon_threads += 1
            self._daemon = False

    def join(self):
        if not self._running: return self._result

        # invent a _join_sleepq if necessary
        if not self._join_sleepq:
            self._join_sleepq = uSleepQueue()

        # and return it; the calling thread will yield it and consequently
        # sleep on it
        return self._join_sleepq

    def start(self):
        assert not self._running

        self._running = True
        if not self._daemon:
            scheduler.non_daemon_threads += 1

        topgen = self._toplevel()
        self._stack = [ topgen ]
        self._stepfn = topgen.next
        self._stepargs = ()

        scheduler.queue(self)

    @staticmethod
    def sleep(timeout):
        uth = scheduler.current_thread
        if not uth._sleep_sleepq:
            uth._sleep_sleepq = uSleepQueue()
        scheduler.monitor.callback_on_timer(time.time() + timeout, uth._sleep_sleepq.wakeone, None)
        yield uth._sleep_sleepq

    def _toplevel(self):
        try:
            result = yield self.run()
        except:
            self._unhandled_exc()
            result = None

        self._finished(result)

        # signal to _step that this _toplevel() has finished
        yield self._finished_thunk

    def _finished(self, result):
        self._running = False
        if not self._daemon:
            scheduler.non_daemon_threads -= 1

        self._result = result

        # start up any and all threads that joined us
        if self._join_sleepq:
            self._join_sleepq.wake(result)

    # a "thunk", yieled to indicate that a uthread has finished
    _finished_thunk = object()

    def _unhandled_exc(self):
        print >>sys.stderr, "Unhandled exception in microthread:"
        traceback.print_exc(file=sys.stderr)

    # Called by uSleepQueue to wake this thread, either with a result
    # or with an exception
    def _wake_thread(self, res=None, exc_info=None):
        if exc_info:
            self._stepfn = self._stack[-1].throw
            self._stepargs = exc_info
            scheduler.queue(self)
        else:
            self._stepfn = self._stack[-1].send
            self._stepargs = (res,)
            scheduler.queue(self)

    def _step(self):
        while True:
            try:
                stepresult = self._stepfn(*self._stepargs)

            except StopIteration, e:
                # generator is done
                assert len(self._stack) > 1, "_toplevel() ended prematurely"
                self._stack.pop()
                self._stepfn = self._stack[-1].send
                if e.args: # if a return value was included, pass it up
                    self._stepargs = (e.args[0],)
                else:
                    self._stepargs = (None,)

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
                if type(stepresult) is types.GeneratorType:
                    # starting a nested generator
                    self._stack.append(stepresult)
                    self._stepfn = self._stack[-1].next
                    self._stepargs = ()
                    # requeue this thread in the interest of cooperation
                    scheduler.queue(self)
                    break
                
                elif stepresult is self._finished_thunk:
                    # uthread (not just generator) is finished
                    assert len(self._stack) == 1, "something other than _toplevel() yielded _finished"
                    self._stack[-1].close() # finish off the _toplevel() generator
                    break
                
                elif type(stepresult) is uSleepQueue:
                    # sleep on a sleep queue
                    stepresult.add(self)
                    break

                else:
                    # bounce any other yielded result back to the generator
                    self._stepfn = self._stack[-1].send
                    self._stepargs = (stepresult,)
                    # use this as a cooperative yield
                    scheduler.queue(self)
                    break

class uMonitor(object):
    """
    uMonitors are responsible for polling for new events and waking
    the SleepQueues associated associated with those events.  uMonitors also
    handle timeouts.

    @ivar pending_writes: a map of filenos to L{uSleepQueue} objects that
    are pending an opportunity to write
    @type pending_writes: dictionary

    @ivar pending_reads: a map of filenos to L{uSleepQueue} objects that
    are pending an opportunity to read
    @type pending_reads: dictionary

    @ivar timers: a L{heapq}-managed list of tuples (waketime, uSleepQueue)
    describing threads sleeping on a timeout.
    """

    def __init__(self):
        self.timerq = [] # TODO: epydoc
        self.timers = {} # TODO: epydoc
        self.last_timer = 0L # TODO: epydoc

        # TODO: epydoc how to use this
        self.callq = []
        self.callq_lock = threading.Lock()
        self.callq_pipe = os.pipe() # TODO: portable?

        self.pending_writes = {}
        self.pending_reads = { self.callq_pipe[0] : (self.callq_activity, ()) }

    ####
    # event loop

    def poll(self, scheduler_idle):
        """
        Poll for new events.  If C{scheduler_idle} is true, then the scheduler
        has no CPU-bound processing to take care of, and this function may
        block.

        @param scheduler_idle: is the scheduler otherwise idle?
        @type scheduler_idle: boolean
        """
        # TODO: use poll where available (switch to "registration")
        # use select() to discover any available IO, and wake
        # any triggered threads, or timed-out timers
        if scheduler_idle:
            if self.timerq:
                timeout = max(0, self.timerq[0][0] - time.time())
            else:
                timeout = None # block until I/O
        else:
            timeout = 0.0 # don't block
        r, w, _ = select.select(self.pending_reads.keys(),
                                self.pending_writes.keys(),
                                [], timeout)

        for fd in r:
            callable, args = self.pending_reads[fd]
            del self.pending_reads[fd]
            callable(*args)
        for fd in w:
            callable, args = self.pending_writes[fd]
            del self.pending_writes[fd]
            callable(*args)

        now = time.time()
        while self.timerq and self.timerq[0][0] < now:
            waketime, timer = heapq.heappop(self.timerq)
            waketime, callable, args = self.timers.pop(timer)
            callable(*args)

    ####
    # callq maintenance

    def call_in_main_thread(self, callable, *args, **kwargs):
        self.callq_lock.acquire()
        try:
            self.callq.append((callable, args, kwargs))

            # only write to the callq pipe if it's possible that there's
            # nothing in it right now; len(callq) should be equal to the
            # number of 'x'es in the pipe buffer
            if len(self.callq) < 10: os.write(self.callq_pipe[1], 'x')
        finally:
            self.callq_lock.release()

    def callq_activity(self):
        # flush the 'x'es out of the callq
        self.callq_lock.acquire()
        try:
            os.read(self.callq_pipe[0], 1024)
            callq, self.callq = self.callq, []
        finally:
            self.callq_lock.release()

        for callable, args, kwargs in callq:
            try:
                callable(*args, **kwargs)
            except:
                self.callq_error(callable, args, kwargs, sys.exc_info())

        # re-register the listen on this fd
        self.pending_reads[self.callq_pipe[0]] = (self.callq_activity, ())

    def callq_error(self, callable, args, kwargs, exc_info):
        print >>sys.stderr, "Error calling %s(*%s, **%s): " % (callable, args, kwargs, exc_info)

    ####
    # fd interface

    def callback_on_read(self, fd, callable, *args):
        self.pending_reads[fd] = (callable, args)

    def callback_on_write(self, fd, callable, *argsNone):
        self.pending_writes[fd] = (callable, args)

    ####
    # timer interface

    # TODO: use a list with bisect instead of heapq?
    def callback_on_timer(self, waketime, callable, *args):
        # TODO: epydoc
        timer = self.last_timer = self.last_timer + 1
        self.timers[timer] = (waketime, callable, args)
        heapq.heappush(self.timerq, (waketime, timer))
        return timer

    def cancel_sleep_callback(self, timer):
        # TODO: epydoc
        waketime, callable, args = self.timers.pop(timer)
        self.timerq.remove((waketime, timer))

scheduler = None
def current_scheduler():
    global scheduler
    if not scheduler: scheduler = uScheduler()
    return scheduler

def current_thread():
    return scheduler.current_thread

# copy class functions into the module namespaces
spawn = uThread.spawn
sleep = uThread.sleep

def run(callable, *args, **kwargs):
    """
    Start up a scheduler by calling C{callable(*args, **kwargs)}.
    """
    # start up the scheduler before starting this thread
    # TODO: need to start it earlier?? init()??
    scheduler = current_scheduler()

    thd = uThread(target=callable, args=args, kwargs=kwargs, name="main")
    thd.start()

    scheduler.run()
