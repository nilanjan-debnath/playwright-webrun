from slowapi import Limiter
from slowapi.util import get_remote_address
from functools import lru_cache
from app.core.config import settings


def setup_limiter():
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=settings.redis_url,
        strategy="moving-window",
        enabled=settings.ratelimit_enabled,
    )
    return limiter


@lru_cache(maxsize=1)
def get_limiter():
    return setup_limiter()


limiter = get_limiter()
