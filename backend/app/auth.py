"""
Authentication for the API.

Every protected route depends on `get_current_user`, which accepts only access tokens this
backend issued (HS256, signed with APP_JWT_SECRET). Clients get one by either:
- exchanging a Microsoft (Azure AD) ID token at /api/auth/microsoft, verified against the
  tenant's JWKS (signature, audience, issuer, tenant id, email domain), or
- signing in with the demo account at /api/auth/demo-login, only when DEMO_LOGIN_ENABLED=true.
"""
import hmac
import logging
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

TOKEN_ALGORITHM = "HS256"
TOKEN_ISSUER = "wpi-adviser"
ADMIN_ROLE = "admin"

_bearer = HTTPBearer(auto_error=False)


@dataclass
class User:
    id: str
    email: str
    name: str
    roles: List[str] = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return ADMIN_ROLE in self.roles


def _env_list(name: str, default: str = "") -> List[str]:
    return [v.strip().lower() for v in os.getenv(name, default).split(",") if v.strip()]


def _jwt_secret() -> str:
    secret = os.getenv("APP_JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("APP_JWT_SECRET must be set to at least 32 characters")
    return secret


def token_ttl_seconds() -> int:
    return int(os.getenv("APP_TOKEN_TTL_SECONDS", 8 * 3600))


def demo_login_enabled() -> bool:
    return os.getenv("DEMO_LOGIN_ENABLED", "false").lower() == "true"


def microsoft_login_enabled() -> bool:
    return bool(os.getenv("AZURE_CLIENT_ID") and os.getenv("AZURE_TENANT_ID"))


def _roles_for(email: str) -> List[str]:
    return [ADMIN_ROLE] if email.lower() in _env_list("ADMIN_EMAILS") else []


def create_access_token(email: str, name: str, subject: Optional[str] = None) -> str:
    """Issue the backend's own access token; the user id is the lower-cased email unless given."""
    now = int(time.time())
    email = email.lower()
    claims = {
        "iss": TOKEN_ISSUER,
        "sub": subject or email,
        "email": email,
        "name": name,
        "roles": _roles_for(email),
        "iat": now,
        "exp": now + token_ttl_seconds(),
    }
    return jwt.encode(claims, _jwt_secret(), algorithm=TOKEN_ALGORITHM)


def decode_access_token(token: str) -> User:
    try:
        claims = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[TOKEN_ALGORITHM],
            issuer=TOKEN_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"}) from exc
    return User(id=claims["sub"], email=claims.get("email", ""), name=claims.get("name", ""),
                roles=list(claims.get("roles") or []))


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    return decode_access_token(credentials.credentials)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    return user


def verify_demo_credentials(email: str, password: str) -> bool:
    expected_email = os.getenv("DEMO_USER_EMAIL", "").lower()
    expected_password = os.getenv("DEMO_USER_PASSWORD", "")
    if not (demo_login_enabled() and expected_email and expected_password):
        return False
    email_ok = hmac.compare_digest(email.lower().encode(), expected_email.encode())
    password_ok = hmac.compare_digest(password.encode(), expected_password.encode())
    return email_ok and password_ok


@lru_cache(maxsize=1)
def _jwks_client(tenant_id: str) -> "jwt.PyJWKClient":
    return jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys")


def verify_microsoft_id_token(id_token: str) -> User:
    """Validate an Azure AD v2 ID token for this app registration and tenant."""
    client_id = os.getenv("AZURE_CLIENT_ID", "")
    tenant_id = os.getenv("AZURE_TENANT_ID", "")
    if not (client_id and tenant_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Microsoft sign-in is not configured")
    try:
        signing_key = _jwks_client(tenant_id).get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            options={"require": ["exp", "iat", "aud", "iss", "tid", "oid"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("Rejected Microsoft ID token: %s", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Microsoft token") from exc

    if claims["tid"] != tenant_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is not in the allowed tenant")
    email = (claims.get("preferred_username") or claims.get("email") or "").lower()
    domains = _env_list("ALLOWED_EMAIL_DOMAINS", "wpi.edu,alumni.wpi.edu")
    if not any(email.endswith("@" + d) for d in domains):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Please use your WPI email address")
    return User(id=f"aad:{claims['oid']}", email=email, name=claims.get("name") or email.split("@")[0],
                roles=_roles_for(email))
