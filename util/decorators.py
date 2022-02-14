import operator
import time
from datetime import datetime, timedelta
from functools import lru_cache, wraps, partial
from threading import Lock
from typing import Callable, Type, Any


def timed_asynchronous_lru_cache(
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

    def wrapper(f: Callable):
        lock = lock_type()
        f = lru_cache(maxsize=maxsize, typed=typed)(f)
        f.delta = timedelta(seconds=timeout)
        f.expiration = datetime.utcnow() + f.delta

        @wraps(f)
        def wrapped(*args, **kwargs):
            with lock:
                if (now := datetime.utcnow()) >= f.expiration:
                    f.cache_clear()
                    f.expiration = now + f.delta
                return f(*args, **kwargs)

        return wrapped

    return wrapper


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
        is_desired_value = partial(operator.eq, cond)

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
