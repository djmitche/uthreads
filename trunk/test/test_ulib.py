"""
  Test cases for uthread
  Dustin J. Mitchell <dustin@cs.uchicago.edu>
"""

import os
import sys
import time
import unittest
import thread
from test.test_support import *

import uthreads
from uthreads import *
from ulib.sync import *
from ulib.socket import *
from ulib.timer import *
from ulib.wrap import *

_exc_in_microthread = None
def setup():
    """
    Apply monkey-patches
    """
    # shunt exceptions in threads on into the unittest machinery
    def _unhandled_exc(self):
        global _exc_in_microthread
        _exc_in_microthread = sys.exc_info()
        current_scheduler().stop()
    uthreads.uThread._unhandled_exc = _unhandled_exc

def uthreaded(*args, **kwargs):
    """
    Decorator to run the decorated function as
    the main uthreads.
    """
    def decorator(test):
        def wraptest(self):
            global _exc_in_microthread
            _exc_in_microthread = None
            uthreads.run(test, self, *args, **kwargs)
            if _exc_in_microthread:
                raise _exc_in_microthread[0], _exc_in_microthread[1], _exc_in_microthread[2]
        return wraptest
    return decorator

class ulibTests(unittest.TestCase):
    def tearDown(self):
        uthreads.uScheduler._scheduler = None

    ##
    # ulib.sync

    @uthreaded()
    def test_Lock(self):
        l = Lock()
        mutable = []
        def a():
            yield l.acquire()
            mutable.append(1)
            l.release()
            yield l.acquire()
            mutable.append(5)
            l.release()
        def b():
            yield l.acquire()
            mutable.append(3)
            l.release()
        tha = spawn(a())
        thb = spawn(b())
        yield tha.join()
        yield thb.join()
        assert mutable == [1,3,5], "mutable is %s" % mutable

    @uthreaded()
    def test_Lock_FIFO(self):
        # make sure the lock is FIFO when it's contended
        l = Lock()
        mutable = []
        def do_append(n):
            for _ in range(n): yield
            yield l.acquire()
            mutable.append(n)
            l.release()
        N = 10
        threads = [ spawn(do_append(n)) for n in range(N) ]
        for thread in threads: yield thread.join()
        assert mutable == range(N), "mutable is %s" % mutable

    @uthreaded()
    def test_Queue(self):
        def producer(q):
            for i in range(10):
                yield q.put(i) 
        def consumer(q):
            for i in range(10):
                for _ in range(30): yield # stall for a while
                j = yield q.get()
                assert i == j, "consumer expected %s, got %s (max_size %s)" % (i, j, q.max_size)

        # try the above producer/consumer with a variety of queue sizes
        for size in [ None ] + range(1, 15, 3):
            q = Queue(size)
            prod = spawn(producer(q))
            cons = spawn(consumer(q))
            yield prod.join()
            yield cons.join()

    @uthreaded()
    def test_Queue_multiconsumer(self):
        def producer(q):
            for i in range(20):
                yield q.put(i)
        def consumer(q):
            items = [ (yield q.get()) for _ in range(5) ]

            # we can only assert that we get items in order, not which particular items this
            # consumer will get
            items_sorted = items[:]
            items_sorted.sort()
            assert items_sorted == items, "consumer got %s, which is not in order" % (items,)

        # try the above producer/consumer with a variety of queue sizes
        for size in [ None ] + range(1, 15, 3):
            q = Queue(size)
            prod = spawn(producer(q))
            consumers = [ spawn(consumer(q)) for _ in range(4) ]
            yield prod.join()
            for cons in consumers:
                yield cons.join()

    @uthreaded()
    def test_Queue_put_nowait(self):
        q = Queue(1)
        q.put_nowait(0)
        self.assertRaises(Full, q.put_nowait, 1)

    @uthreaded()
    def test_Queue_gut_nowait(self):
        q = Queue()
        self.assertRaises(Empty, q.get_nowait)

    ##
    # ulib.timer

    @uthreaded()
    def test_Timer(self):
        mutable = []
        t = Timer()
        def timesup(mut):
            yield
            mut.append(1)
        t.set(0.1, timesup(mutable))
        assert mutable != [1], "timer fired too early"
        now = time.time()
        yield sleep(0.3)
        assert time.time() >= now + 0.2, "sleep() isn't working, so I can't test Timer"
        assert mutable == [1], "timer didn't fire"

    @uthreaded()
    def test_Timer_clear(self):
        mutable = []
        t = Timer()
        def timesup(mut):
            yield
            mut.append(1)
        t.set(0.1, timesup(mutable))
        assert mutable != [1], "timer fired too early"
        yield
        t.clear()
        now = time.time()
        yield sleep(0.3)
        assert time.time() >= now + 0.2, "sleep() isn't working, so I can't test Timer"
        assert mutable != [1], "cleared timer fired"

    ##
    # ulib.wrap

    @uthreaded()
    def test_uWrap(self):
        import thread
        dec = uWrap()

        @dec
        def run_me_in_another_thread():
            return thread.get_ident()

        other_ident = ( yield run_me_in_another_thread() )
        assert other_ident != thread.get_ident(), "function ran in the main thread"

    @uthreaded()
    def test_uWrap_multi(self):
        dec = uWrap()
        @dec
        def run_me_in_another_thread():
            time.sleep(0.1)
            return thread.get_ident()

        # this is unrealistically silly, but there you are..
        th1 = yield spawn(run_me_in_another_thread())
        th2 = yield spawn(run_me_in_another_thread())
        other_ident = yield th1.join()
        another_ident = yield th2.join()
        assert other_ident != thread.get_ident(), "first call ran in the main thread"
        assert another_ident != thread.get_ident(), "second call ran in the main thread"
        assert other_ident != another_ident, "both calls ran in same thread"

    ##
    # ulib.socket

    @uthreaded()
    def dont_test_connect(self):
        s = socket(AF_INET, SOCK_STREAM)
        print "connecting"
        yield s.connect(("", 22))
        print "reading"
        v = yield s.recv(1024)
        print "read", repr(v)
        print "reading"
        v = yield s.recv(1024)
        print "read", repr(v)
        s.close()

if __name__ == "__main__":
    setup()
    run_unittest(ulibTests)
