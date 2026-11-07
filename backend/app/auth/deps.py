from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .service import User

# Shows the "Authorize" button in Swagger. auto_error=False so a missing token gives our own 401 message.
bearer_scheme = HTTPBearer(auto_error=False, description="Session token from POST /api/auth/verify-otp")


def bearer_token(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> Optional[str]:
    return creds.credentials.strip() if creds and creds.credentials else None


def current_user(request: Request, token: Optional[str] = Depends(bearer_token)) -> User:
    user = request.app.state.auth.user_for_token(token)
    if user is None:
        raise HTTPException(401, "Please sign in")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user
