import asyncio
import functools
import random
from typing import Any, Callable, TypeVar

from loguru import logger

T = TypeVar("T")


def retry(max_attempts: int = 3,
          base_delay: float = 30.0,
          max_delay: float = 300.0,
          exceptions: tuple = (Exception,),
          on_retry: Callable[[Exception, int], None] = None):
    """
    重试装饰器

    指数退避策略：base_delay * (2 ** attempt) + random_jitter
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        raise

                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    total_delay = delay + jitter

                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__} "
                        f"after {total_delay:.1f}s: {e}"
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    await asyncio.sleep(total_delay)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        raise

                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    total_delay = delay + jitter

                    logger.warning(
                        f"Retry {attempt}/{max_attempts} for {func.__name__} "
                        f"after {total_delay:.1f}s: {e}"
                    )

                    if on_retry:
                        on_retry(e, attempt)

                    import time
                    time.sleep(total_delay)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def weighted_choice(choices: list, weights: list) -> Any:
    """根据权重随机选择"""
    assert len(choices) == len(weights)
    total = sum(weights)
    r = random.uniform(0, total)
    upto = 0
    for choice, weight in zip(choices, weights):
        if upto + weight >= r:
            return choice
        upto += weight
    return choices[-1]
