import asyncio
from typing import Any, Callable


async def run_with_timeout(
    func: Callable[..., Any], *args: Any, timeout: float = 5.0, **kwargs: Any
) -> Any:
    """Run a blocking or async function with a timeout."""
    try:
        if asyncio.iscoroutinefunction(func):
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args, **kwargs), timeout=timeout
        )
    except asyncio.TimeoutError:
        raise
