from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class UserAccount:
    user_id: str
    email: str
    password_hash: str
    role: str = "member"


@dataclass(frozen=True)
class SessionToken:
    token_id: str
    user_id: str
    expires_at: int
    is_revoked: bool = False
