import time
from functools import lru_cache, wraps
from threading import Lock
from time import monotonic_ns
from typing import Callable, Type, Any


class timed_asynchronous_lru_cache:
    def __init__(
        self,
        timeout: int = 300,
        maxsize: int = 128,
        typed: bool = False,
        lock_type: Type[Lock] = Lock,
    ):
        """
        Extension of functools lru_cache with a timeout

        Parameters:
        timeout: Timeout in seconds to clear the WHOLE cache, default 5 minutes
        maxsize: Maximum number of items in the cache
        typed: Equal values of different types will be considered
               different entries in the cache
        lock_type: Class which implements a Lock,
                   to be instantiated once per wrapped function

        Extension of code posted here:
        https://gist.github.com/Morreski/c1d08a3afa4040815eafd3891e16b945
        """

        self.lock = lock_type()

        def wrapper_cache(f: Callable):
            with self.lock:
                cache = lru_cache(maxsize=maxsize, typed=typed)(f)
                cache.delta = timeout * 10 ** 9
                cache.expiration = monotonic_ns() + cache.delta

                @wraps(cache)
                def wrapped_f(*args, **kwargs):
                    if monotonic_ns() >= cache.expiration:
                        cache.cache_clear()
                        f.expiration = monotonic_ns() + cache.delta
                    return f(*args, **kwargs)

                wrapped_f.cache_info = cache.cache_info
                wrapped_f.cache_clear = cache.cache_clear
                return wrapped_f

        self.wrapper_cache = wrapper_cache

    def __call__(self, _func=None):
        # To allow decorator to be used without arguments
        if _func is None:
            return self.wrapper_cache
        else:
            return self.wrapper_cache(_func)


def retry(
    n: int = 5, cond: Any = True, wait: float = 0, msg: str = "Unknown failure."
) -> Callable:
    """
    Retry a function until it passes a desired condition. The condition can either
    be a value or a callable, which evaluates the function's return itself.

    By default, retries 5 times and doesn't wait between retries.

    If the function never succeeds, raises ``TimeoutError`` with ``msg``.
    """
    if hasattr(cond, "__call__"):
        is_desired_value = cond
    else:
        is_desired_value = lambda x: x == cond

    def decorator(f: Callable):
        def retry_f(*args, **kwargs):
            if n < 1:
                raise ValueError(f"Retries must be positive, non-zero integer: {n}")
            error = None
            # + 1 because we want 1 initial try, and then retry n times
            for i in range(total_attempts := n + 1):
                try:
                    if is_desired_value(res := f(*args, **kwargs)):
                        return res
                except Exception as e:
                    error = e
                # Don't sleep after the last attempt
                if i < total_attempts:
                    time.sleep(wait)

            if error:
                raise error
            else:
                raise TimeoutError(msg)

        return retry_f

    return decorator
