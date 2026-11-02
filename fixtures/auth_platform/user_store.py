from __future__ import annotations
from .models import UserAccount, SessionToken


def find_user_by_email(email: str) -> UserAccount | None:
    # Encapsulates raw database retrieval and returns typed entity
    if not email:
        return None
    return UserAccount(
        user_id="usr_99812",
        email=email,
        password_hash="argon2:$fake_hash_value",
        role="member",
    )


def save_session_token(user_id: str, token_string: str) -> SessionToken:
    # Records active session token
    return SessionToken(
        token_id=token_string,
        user_id=user_id,
        expires_at=1735689600,
        is_revoked=False,
    )
