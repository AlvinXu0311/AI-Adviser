"""
Sign-in endpoints. Both flows set the backend's own token as an HttpOnly cookie (see app/auth.py);
the token is never returned to page scripts.
"""
import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from ..auth import (
    COOKIE_NAME,
    User,
    cookie_secure,
    create_access_token,
    demo_login_enabled,
    get_current_user,
    microsoft_login_enabled,
    revoke_token,
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
    expires_in: int
    email: str
    name: str
    roles: list[str]


def _token_response(user: User, response: Response) -> TokenResponse:
    token = create_access_token(user.email, user.name, subject=user.id)
    response.set_cookie(COOKIE_NAME, token, max_age=token_ttl_seconds(), path="/api",
                        httponly=True, secure=cookie_secure(), samesite="strict")
    return TokenResponse(expires_in=token_ttl_seconds(), email=user.email, name=user.name, roles=user.roles)


@router.get("/config")
async def auth_config():
    """Which sign-in methods the login page should offer."""
    return {"demo_login": demo_login_enabled(), "microsoft_login": microsoft_login_enabled()}


@router.post("/demo-login", response_model=TokenResponse)
async def demo_login(request: DemoLoginRequest, http_request: Request, response: Response) -> TokenResponse:
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
    return _token_response(User(id=email, email=email, name="Demo User"), response)


@router.post("/microsoft", response_model=TokenResponse)
async def microsoft_login(request: MicrosoftLoginRequest, http_request: Request,
                          response: Response) -> TokenResponse:
    await asyncio.to_thread(rate_limit.hit, f"ratelimit:microsoft-login:{rate_limit.client_ip(http_request)}",
                            int(os.getenv("MICROSOFT_LOGIN_RATE_LIMIT_PER_MINUTE", 20)), 60)
    # JWKS fetch is a blocking HTTP call (cached after the first one)
    user = await asyncio.to_thread(verify_microsoft_id_token, request.id_token)
    return _token_response(user, response)


@router.post("/logout")
async def logout(response: Response, user: User = Depends(get_current_user)):
    """Revoke the current token server-side and clear the cookie."""
    await asyncio.to_thread(revoke_token, user)
    response.delete_cookie(COOKIE_NAME, path="/api", httponly=True, secure=cookie_secure(), samesite="strict")
    return {"status": "signed_out"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": user.name, "roles": user.roles}
