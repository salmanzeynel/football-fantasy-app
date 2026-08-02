"""Accounts.

Phase 1 is local and single-household: no email verification, no password reset, no
OAuth. Those arrive only if the app is ever hosted (docs/PLAN.md section 1).
"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models.base import utcnow


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    display_name: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
