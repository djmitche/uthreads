"""
  Test cases for uthread
  Dustin J. Mitchell <dustin@cs.uchicago.edu>
"""

import os
import sys
import time
import unittest
from test.test_support import *

import uthread
from uthread import *

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
    uthread.uThread._unhandled_exc = _unhandled_exc

def uthreaded(*args, **kwargs):
    """
    Decorator to run the decorated function as
    the main uthread.
    """
    def decorator(test):
        def wraptest(self):
            global _exc_in_microthread
            _exc_in_microthread = None
            uthread.run(test, self, *args, **kwargs)
            if _exc_in_microthread:
                raise _exc_in_microthread[0], _exc_in_microthread[1], _exc_in_microthread[2]
        return wraptest
    return decorator

class uThreadTests(unittest.TestCase):
    def tearDown(self):
        uthread.uScheduler._scheduler = None

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

if __name__ == "__main__":
    setup()
    run_unittest(uThreadTests)
