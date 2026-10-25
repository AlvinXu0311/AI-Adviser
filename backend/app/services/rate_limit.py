"""
Redis fixed-window rate limits, shared by every backend worker.

- Per-user request budgets for the expensive (LLM-backed) routes, via `rate_limited(...)`.
- Login lockout: after LOGIN_MAX_FAILURES failed demo logins, the email and the client IP
  are each locked out for LOGIN_LOCKOUT_SECONDS.

Limits are read from the environment on every call, so tests and deployments can tune them.
"""
import asyncio
import logging
import os
from typing import Callable

from fastapi import Depends, HTTPException, Request, status

from ..auth import User, get_current_user
from .conversation_memory import get_conversation_memory

logger = logging.getLogger(__name__)


def _redis():
    return get_conversation_memory().redis_client


def _too_many(retry_after: int, message: str) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, message,
                         headers={"Retry-After": str(max(retry_after, 1))})


def hit(key: str, limit: int, window_seconds: int) -> None:
    """Count one request against `key`; raise 429 once more than `limit` land in the window."""
    redis = _redis()
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_seconds, nx=True)
    pipe.ttl(key)
    count, _, ttl = pipe.execute()
    if count > limit:
        raise _too_many(ttl, "Too many requests. Please slow down and try again shortly.")


def rate_limited(scope: str, limit_env: str, default_limit: int, window_seconds: int) -> Callable:
    """Dependency: authenticate, then charge one request to this user's `scope` budget."""
    async def dependency(user: User = Depends(get_current_user)) -> User:
        limit = int(os.getenv(limit_env, default_limit))
        if limit > 0:
            await asyncio.to_thread(hit, f"ratelimit:{scope}:{user.id}", limit, window_seconds)
        return user
    return dependency


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers already resolved X-Forwarded-For from nginx into request.client
    return request.client.host if request.client else "unknown"


def _login_keys(email: str, ip: str) -> list[str]:
    return [f"ratelimit:login-fail:email:{email.lower()}", f"ratelimit:login-fail:ip:{ip}"]


def check_login_allowed(email: str, ip: str) -> None:
    """Raise 429 while the email or the IP is locked out after repeated failures."""
    limit = int(os.getenv("LOGIN_MAX_FAILURES", 5))
    redis = _redis()
    for key in _login_keys(email, ip):
        failures = redis.get(key)
        if failures is not None and int(failures) >= limit:
            raise _too_many(redis.ttl(key), "Too many failed sign-in attempts. Try again later.")


def record_login_failure(email: str, ip: str) -> None:
    lockout = int(os.getenv("LOGIN_LOCKOUT_SECONDS", 900))
    pipe = _redis().pipeline()
    for key in _login_keys(email, ip):
        pipe.incr(key)
        pipe.expire(key, lockout)
    pipe.execute()
    logger.info("Failed demo login from %s", ip)


def record_login_success(email: str) -> None:
    # Clear only the email counter; the IP counter keeps limiting guessing across accounts
    _redis().delete(_login_keys(email, "")[0])
