import functools
import logging
import time

logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries=3, delays=(2, 5, 10)):
    """
    Retry decorator for functions that may raise transient exceptions.
    Retries up to `max_retries` times with increasing `delays` on failure.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        delay = delays[attempt] if attempt < len(delays) else delays[-1]
                        logger.warning(
                            "Exception in %s: %s. Retrying in %ds (Attempt %d/%d)...",
                            func.__name__,
                            str(exc),
                            delay,
                            attempt + 1,
                            max_retries
                        )
                        time.sleep(delay)
                    else:
                        logger.error("Failed %s after %d attempts: %s", func.__name__, max_retries, exc)
            raise last_exc
        return wrapper
    return decorator
