from __future__ import annotations

import hmac

from KGTS.models.auth import LoginRequest
from KGTS.config import get_auth_config


def verify_login_credentials(request: LoginRequest, role: str) -> dict[str, str] | None:
    auth = get_auth_config(role)
    if not auth["password"]:
        return None
    username_ok = hmac.compare_digest(request.username, auth["username"])
    password_ok = hmac.compare_digest(request.password, auth["password"])
    if not (username_ok and password_ok):
        return None
    return auth
