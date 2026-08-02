"""Password hashing and credential checks.

Argon2id is the default from argon2-cffi. Nothing here touches the web layer, so it is
testable on its own and reusable from the CLI.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlmodel import Session, func, select

from app.models.identity import User

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8


class AuthError(Exception):
    """Raised for anything a user could plausibly fix by retyping."""


def normalise_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return True


def get_by_email(session: Session, email: str) -> User | None:
    return session.exec(select(User).where(User.email == normalise_email(email))).first()


def register(session: Session, *, email: str, password: str, display_name: str) -> User:
    email = normalise_email(email)
    display_name = display_name.strip()

    if "@" not in email or "." not in email.split("@")[-1]:
        raise AuthError("That does not look like an email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if not display_name:
        raise AuthError("Pick a display name - it is what other managers will see.")
    if get_by_email(session, email) is not None:
        raise AuthError("An account with that email already exists.")

    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate(session: Session, *, email: str, password: str) -> User:
    user = get_by_email(session, email)
    # Hash even when the user is missing, so a wrong email and a wrong password take
    # roughly the same time and the response cannot be used to enumerate accounts.
    if user is None:
        hash_password(password)
        raise AuthError("Email or password is incorrect.")
    if not verify_password(user.password_hash, password):
        raise AuthError("Email or password is incorrect.")
    if not user.is_active:
        raise AuthError("That account is disabled.")
    return user


def user_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(User)).one()
