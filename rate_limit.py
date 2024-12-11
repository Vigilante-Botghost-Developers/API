from fastapi import Request
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis
import os
from auth import UserFlag, get_user_flags, RateLimits

async def setup_rate_limiter():
    """Initialize the Redis connection for rate limiting."""
    redis_instance = redis.from_url(os.getenv("REDIS_URL"), encoding="utf-8", decode_responses=True)
    await FastAPILimiter.init(redis_instance)

async def dynamic_rate_limit(request: Request):
    """Get rate limit based on user flags."""
    api_key = request.headers.get("X-API-Key")
    user_flags = await get_user_flags(api_key)
    
    if not user_flags:
        return RateLimiter(times=RateLimits.UNAUTHENTICATED_LIMIT, minutes=1)
    
    # Get the highest rate limit from user's flags
    rate_limit = RateLimits.UNAUTHENTICATED_LIMIT
    for flag in user_flags:
        flag_limit = RateLimits.FLAG_LIMITS.get(flag, 0)
        if flag_limit == -1:  # Unlimited for SYSTEM_OPERATOR
            return None
        rate_limit = max(rate_limit, flag_limit)
    
    return RateLimiter(times=rate_limit, minutes=1)
