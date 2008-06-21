"""
  Test cases for uthreads
  Dustin J. Mitchell <dustin@cs.uchicago.edu>
"""

import os
import sys
import time
import thread
from test.test_support import *
from twisted.internet import defer
from twisted.trial import unittest

import uthreads
from uthreads import *
from uthreads.sync import *
from uthreads.socket import *
from uthreads.timer import *
from uthreads.wrap import *

def uthreaded(*args, **kwargs):
    """
    Decorator to run the decorated function as a uthread.
    """
    def decorator(test):
        def wraptest(self):
            return run(test, self, *args, **kwargs)
        wraptest.func_name = test.func_name
        return wraptest
    return decorator

class basic(unittest.TestCase):
    def test_main(self):
        mutable = []
        def main():
            yield
            mutable.append(1)
            yield
        def check(res):
            assert mutable == [1], "mutable is %s" % mutable
        return run(main).addCallback(check)

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
    def test_names(self):
        def short():
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
        mutable = [0]
        def thread_fn():
            # a busy-loop is inefficient, but exercises minimal
            # other functionality
            while not mutable[0]:
                yield
        th = spawn(thread_fn())
        assert th.isAlive()
        mutable[0] = 1
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

class sync(unittest.TestCase):
    @uthreaded()
    def test_Lock(self):
        l = Lock()
        mutable = []
        def a():
            yield l.acquire()
            mutable.append(1)
            yield sleep(0.15)
            mutable.append(2)
            yield l.release()

            yield l.acquire()
            mutable.append(5)
            yield l.release()

        def b():
            yield sleep(0.1)

            yield l.acquire()
            mutable.append(3)
            yield sleep(0.1)
            mutable.append(4)
            yield l.release()

        tha = spawn(a())
        thb = spawn(b())
        yield tha.join()
        yield thb.join()
        assert mutable == [1,2,3,4,5], "mutable is %s" % mutable

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

class timer(unittest.TestCase):
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
