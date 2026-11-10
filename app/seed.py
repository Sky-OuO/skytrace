"""导入词表、演示帐号和 10 个对象 stub。可以重复执行。"""

import asyncio

from fastapi_users.password import PasswordHelper
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import select

from app.catalog import SUBJECT_STUBS, TAGS
from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.models import Subject, Tag, User


async def _upsert_user(session: AsyncSession, helper: PasswordHelper, email: str, password: str, name: str, role: str) -> User:
    email = email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    hashed = helper.hash(password)
    if user is None:
        user = User(
            email=email,
            hashed_password=hashed,
            display_name=name,
            role=role,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        session.add(user)
        await session.flush()
        return user
    user.hashed_password = hashed
    user.display_name = name
    user.role = role
    user.is_active = True
    user.is_verified = True
    return user


async def seed() -> None:
    settings = get_settings()
    engine: AsyncEngine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    helper = PasswordHelper()
    async with factory() as session:
        author = await _upsert_user(
            session,
            helper,
            settings.demo_author_email,
            settings.demo_author_password,
            settings.demo_author_name,
            "author",
        )
        await _upsert_user(
            session,
            helper,
            settings.demo_reviewer_email,
            settings.demo_reviewer_password,
            settings.demo_reviewer_name,
            "reviewer",
        )
        for facet, slug, name in TAGS:
            found = await session.execute(select(Tag).where(Tag.slug == slug))
            tag = found.scalar_one_or_none()
            if tag is None:
                session.add(Tag(slug=slug, name=name, facet=facet))
            else:
                tag.name = name
                tag.facet = facet
        for stub in SUBJECT_STUBS:
            found = await session.execute(select(Subject).where(Subject.slug == stub["slug"]))
            subject = found.scalar_one_or_none()
            if subject is None:
                session.add(
                    Subject(
                        slug=stub["slug"],
                        name=stub["name"],
                        type=stub["type"],
                        primary_channel=stub["primary_channel"],
                        condition_axes=list(stub["condition_axes"]),
                        created_by=author.id,
                    )
                )
            else:
                subject.name = stub["name"]
                subject.type = stub["type"]
                subject.primary_channel = stub["primary_channel"]
                subject.condition_axes = list(stub["condition_axes"])
                if subject.created_by is None:
                    subject.created_by = author.id
        await session.commit()
    await engine.dispose()
    print(f"种子已写入：{len(TAGS)} 个标签，{len(SUBJECT_STUBS)} 个对象，2 个演示帐号。")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
