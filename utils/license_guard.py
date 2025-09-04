"""Decorators for enforcing license features."""

from __future__ import annotations

import functools
import inspect

from fastapi import HTTPException

from config import config


# require_feature routine
def require_feature(feature_name: str):
    """Ensure ``feature_name`` is enabled in ``config['features']``."""

    # wrapper routine
    def wrapper(fn):
        @functools.wraps(fn)
        async def inner(*args, **kwargs):
            if not config.get("features", {}).get(feature_name, False):
                raise HTTPException(
                    status_code=403,
                    detail=f"Feature {feature_name} not licensed",
                )
            return await fn(*args, **kwargs)

        inner.__signature__ = inspect.signature(fn, eval_str=True)

        return inner

    return wrapper


__all__ = ["require_feature"]
