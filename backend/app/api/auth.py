"""
Sign-in endpoints. Both flows return the backend's own bearer token (see app/auth.py).
"""
import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..auth import (
    User,
    create_access_token,
    demo_login_enabled,
    get_current_user,
    microsoft_login_enabled,
    token_ttl_seconds,
    verify_demo_credentials,
    verify_microsoft_id_token,
)
from ..services import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()


class DemoLoginRequest(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=256)


class MicrosoftLoginRequest(BaseModel):
    id_token: str = Field(..., max_length=16384)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    email: str
    name: str
    roles: list[str]


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(user.email, user.name, subject=user.id)
    return TokenResponse(access_token=token, expires_in=token_ttl_seconds(),
                         email=user.email, name=user.name, roles=user.roles)


@router.get("/config")
async def auth_config():
    """Which sign-in methods the login page should offer."""
    return {"demo_login": demo_login_enabled(), "microsoft_login": microsoft_login_enabled()}


@router.post("/demo-login", response_model=TokenResponse)
async def demo_login(request: DemoLoginRequest, http_request: Request) -> TokenResponse:
    if not demo_login_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demo login is disabled")
    ip = rate_limit.client_ip(http_request)
    # Locked out after LOGIN_MAX_FAILURES failures per email or per IP (Redis, all workers)
    await asyncio.to_thread(rate_limit.check_login_allowed, request.email, ip)
    if not verify_demo_credentials(request.email, request.password):
        await asyncio.to_thread(rate_limit.record_login_failure, request.email, ip)
        # Small flat delay on top of the lockout slows down guessing within the budget
        await asyncio.sleep(1)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    await asyncio.to_thread(rate_limit.record_login_success, request.email)
    email = request.email.lower()
    return _token_response(User(id=email, email=email, name="Demo User"))


@router.post("/microsoft", response_model=TokenResponse)
async def microsoft_login(request: MicrosoftLoginRequest, http_request: Request) -> TokenResponse:
    await asyncio.to_thread(rate_limit.hit, f"ratelimit:microsoft-login:{rate_limit.client_ip(http_request)}",
                            int(os.getenv("MICROSOFT_LOGIN_RATE_LIMIT_PER_MINUTE", 20)), 60)
    # JWKS fetch is a blocking HTTP call (cached after the first one)
    user = await asyncio.to_thread(verify_microsoft_id_token, request.id_token)
    return _token_response(user)


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": user.name, "roles": user.roles}
