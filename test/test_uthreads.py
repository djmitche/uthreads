"""
  Test cases for uthreads
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
from uthreads.sync import *
from uthreads.socket import *
from uthreads.timer import *
from uthreads.wrap import *

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

class uThreadTests(unittest.TestCase):
    def tearDown(self):
        uthreads.uScheduler._scheduler = None

    ##
    # Basic ("unit", no less) tests

    def test_main(self):
        mutable = []
        def main():
            mutable.append(1)
            yield
        run(main)
        assert mutable == [1], "mutable is %s" % mutable

    @uthreaded(1, z=3, y=2)
    def test_run_w_args(self, x, y, z):
        assert x == 1 and y == 2 and z == 3
        yield

    @uthreaded()
    def test_run_nongenerator(self):
        pass

    @uthreaded()
    def test_nested_generators(self):
        def recur(x):
            if x != 0:
                yield recur(x-1)
        yield recur(10)

    @uthreaded()
    def test_result(self):
        def foo(x):
            raise StopIteration(3 * x)
        assert (yield foo(5)) == 15

    @uthreaded()
    def test_current_thread(self):
        def other_thread():
            assert current_thread() is th
            yield # make it a generator
        th = spawn(other_thread())

    @uthreaded()
    def test_join1(self):
        def other_thread():
            for _ in range(10): yield
            raise StopIteration(3)
        th = spawn(other_thread())
        assert (yield th.join()) == 3

    @uthreaded()
    def test_join2(self):
        def other_thread():
            raise StopIteration(3)
        th = spawn(other_thread())
        for _ in range(10): yield
        assert (yield th.join()) == 3

    @uthreaded()
    def test_spawn(self):
        mutable = {}
        def func(n):
            for _ in range(n): yield
            mutable[1] = 2
        mutable[1] = 1
        th = spawn(func(10))
        yield # wait a little bit..
        yield
        assert mutable[1] == 1

    @uthreaded()
    def test_setdaemon(self):
        def forever():
            while True: yield
        th = spawn(forever())
        th.setDaemon(True)
        # for this test, failure == non-termination..

    @uthreaded()
    def test_names(self):
        def short():
            yield
            yield
        assert current_thread().getName() == 'main'
        th = spawn(short())
        th.setName('short')
        assert th.getName() == 'short'

    @uthreaded()
    def test_exception(self):
        def fn_raises_RuntimeError():
            yield
            raise RuntimeError
        try:
            yield fn_raises_RuntimeError()
        except RuntimeError:
            pass
        else:
            raise TestFailed, "exception not caught"

    @uthreaded()
    def test_isAlive(self):
        def thread_fn():
            yield
        th = spawn(thread_fn())
        assert th.isAlive()
        yield th.join()
        assert not th.isAlive()

    @uthreaded()
    def test_uThread_subclass(self):
        class MyUThread(uThread):
            def count(self, n):
                for _ in range(n): yield

            def run(self):
                yield self.count(5)
                raise StopIteration(4)

        th = MyUThread()
        th.start()
        assert (yield th.join()) == 4

    @uthreaded()
    def test_sleep(self):
        start = time.time()
        yield sleep(0.5)
        end = time.time()
        assert 0.25 <= (end - start) <= 0.75

    @uthreaded()
    def test_multisleep(self):
        mutable = []
        def sleep_n_append(n):
            current_thread().setName("sna(%s)" % n)
            yield sleep(n / 4.0 + 1)
            mutable.append(n)
        N = 3
        rng = range(N)

        # start in reverse order, just to be sure
        rev = rng[:]
        rev.reverse()
        threads = [ (yield spawn(sleep_n_append(n))) for n in rev ]
        for thread in threads:
            yield thread.join()
        assert mutable == range(N), "mutable is %s" % mutable

    ##
    # More complex tests (compound functionality)

    @uthreaded()
    def test_fibonacci(self):
        def fib(n):
            if n <= 1: raise StopIteration(1)
            raise StopIteration((yield fib(n-1)) + (yield fib(n-2)))
        assert (yield fib(6)) == 13

class ulibTests(unittest.TestCase):
    def tearDown(self):
        uthreads.uScheduler._scheduler = None

    ##
    # uthreads.sync

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
    # uthreads.timer

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
    # uthreads.wrap

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

if __name__ == "__main__":
    setup()
    run_unittest(uThreadTests)
    run_unittest(ulibTests)
