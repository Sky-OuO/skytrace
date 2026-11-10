import uuid
from collections.abc import AsyncIterator
from types import SimpleNamespace

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.manager import UserManager
from app.config import get_settings
from app.db import get_session
from app.errors import ApiError
from app.models import AccessToken, User


async def get_user_db(session: AsyncSession = Depends(get_session)) -> AsyncIterator[SQLAlchemyUserDatabase]:
    yield SQLAlchemyUserDatabase(session, User)


async def get_access_token_db(
    session: AsyncSession = Depends(get_session),
) -> AsyncIterator[SQLAlchemyAccessTokenDatabase]:
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
) -> AsyncIterator[UserManager]:
    yield UserManager(user_db)


def get_database_strategy(
    access_token_db: SQLAlchemyAccessTokenDatabase = Depends(get_access_token_db),
) -> DatabaseStrategy:
    lifetime = get_settings().session_lifetime_seconds
    return DatabaseStrategy(access_token_db, lifetime_seconds=lifetime)


def credentials_for(email: str, password: str) -> OAuth2PasswordRequestForm:
    return OAuth2PasswordRequestForm(
        grant_type="password",
        username=email.strip().lower(),
        password=password,
        scope="",
        client_id=None,
        client_secret=None,
    )


async def get_optional_user(
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
    strategy: DatabaseStrategy = Depends(get_database_strategy),
) -> User | None:
    token = request.cookies.get(get_settings().session_cookie_name)
    user = None
    if token:
        user = await strategy.read_token(token, user_manager)
        if user is not None and not user.is_active:
            user = None
    request.state.current_user = (
        None
        if user is None
        else SimpleNamespace(id=user.id, display_name=user.display_name, role=user.role)
    )
    return user


async def require_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise ApiError(401, "UNAUTHENTICATED", "请先登录")
    return user


async def require_reviewer(user: User = Depends(require_user)) -> User:
    if user.role != "reviewer":
        raise ApiError(403, "FORBIDDEN", "只有审核员可以执行该操作")
    return user


def parse_uuid(value: str, message: str = "标识格式不正确") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ApiError(400, "VALIDATION_ERROR", message) from exc
