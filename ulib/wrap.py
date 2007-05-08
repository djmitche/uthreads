import threading
from uthreads import *

__all__ = [
    'uWrap',
    ]

# TODO: send stop signal

class uWrap(object):
    """
    A decorator to execute one or more functions in a thread.
    XXX more
    """
    def __init__(self, max_threads=None, thread_basename='uWrap'):
        self.max_threads = max_threads
        self.thread_basename = thread_basename
        self.threads = []
        self.num_running_threads = 0
        self.send_queue = []
        self.send_cvar = threading.Condition()

    def __call__(self, fn):
        def wrapper(*args, **kwargs):
            res = ( yield self._run_fn(fn, args, kwargs) )
            raise StopIteration(res)
        wrapper.__doc__ = fn.__doc__
        return wrapper

    def _run_fn(self, fn, args, kwargs):
        # expand the thread pool if it's busy
        self.send_cvar.acquire()
        if (not self.max_threads or len(self.threads) < self.max_threads) and self.num_running_threads + len(self.send_queue) >= len(self.threads):
            th = threading.Thread(target=self._worker_thread, 
                    name='%s-%s' % (self.thread_basename, len(self.threads)+1))
            th.setDaemon(True)
            th.start()
            self.threads.append(th)
        self.send_cvar.release()

        sleepq = uSleepQueue()

        self.send_cvar.acquire()
        self.send_queue.append((sleepq, fn, args, kwargs))
        self.send_cvar.notify()
        self.send_cvar.release()

        return sleepq

    def _worker_thread(self):
        while True:
            # get a task from the queue and increment the number of
            # running threads
            self.send_cvar.acquire()
            while not self.send_queue:
                self.send_cvar.wait()
            sleepq, fn, args, kwargs = self.send_queue.pop(0)
            self.num_running_threads += 1
            self.send_cvar.release()

            # run the task
            try:
                result = fn(*args, **kwargs)
            except:
                current_scheduler().monitor.call_in_main_thread(sleepq.throw, sys.exc_info)
            else:
                current_scheduler().monitor.call_in_main_thread(sleepq.wake, result)

            # decrement num_running_threads
            self.send_cvar.acquire()
            self.num_running_threads -= 1
            self.send_cvar.release()
