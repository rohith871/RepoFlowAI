from __future__ import annotations
from .security import verify_credentials, issue_user_session


def login_endpoint(email: str, password: str) -> dict[str, str]:
    # Public HTTP authentication endpoint
    if not email or not password:
        return {"error": "Invalid payload"}

    user = verify_credentials(email, password)
    if not user:
        return {"error": "Invalid credentials"}

    session = issue_user_session(user)
    return {"token": session.token_id, "user_id": user.user_id, "status": "authenticated"}
