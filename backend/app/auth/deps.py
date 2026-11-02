from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from .service import User


def bearer_token(authorization: Optional[str] = Header(default=None)) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(request: Request, token: Optional[str] = Depends(bearer_token)) -> User:
    user = request.app.state.auth.user_for_token(token)
    if user is None:
        raise HTTPException(401, "Please sign in")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return user
