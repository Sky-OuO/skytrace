"""按 seeds/subjects.json 导入题材、示例和演示帐号。可以重复执行。"""

import argparse
import asyncio
import json
from pathlib import Path

from fastapi_users.password import PasswordHelper
from pydantic import ValidationError
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import select

from app.catalog import TAGS
from app.config import get_settings
from app.db import ensure_schema, make_engine, make_session_factory
from app.domain import UNSORTED_SLUG, SubjectGuide, SubjectSeed
from app.models import Note, Subject, SubjectExample, SubjectTag, Tag, User

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUBJECTS = ROOT / "seeds" / "subjects.json"


async def _upsert_user(
    session: AsyncSession,
    helper: PasswordHelper,
    email: str,
    password: str,
    name: str,
    role: str,
) -> User:
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


def load_subject_seeds(path: Path) -> list[SubjectSeed]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit(f"{path} 必须是题材数组")
    seeds: list[SubjectSeed] = []
    slugs: set[str] = set()
    for index, item in enumerate(raw, start=1):
        try:
            seed = SubjectSeed.model_validate(item)
        except ValidationError as exc:
            raise SystemExit(f"{path} 第 {index} 条不合法：{exc}") from exc
        if seed.slug == UNSORTED_SLUG:
            raise SystemExit("unsorted 是系统隐藏题材，不能写进种子文件")
        if seed.slug in slugs:
            raise SystemExit(f"slug 重复：{seed.slug}")
        slugs.add(seed.slug)
        seeds.append(seed)
    if not 30 <= len(seeds) <= 50:
        raise SystemExit(f"题材数量要在 30 到 50 之间，当前是 {len(seeds)}")
    return seeds


async def _upsert_subject(session: AsyncSession, seed: SubjectSeed, author_id) -> Subject:
    result = await session.execute(select(Subject).where(Subject.slug == seed.slug))
    subject = result.scalar_one_or_none()
    guide = seed.guide.model_dump()
    if subject is None:
        subject = Subject(
            slug=seed.slug,
            name=seed.name,
            type=seed.resolved_type(),
            primary_channel=seed.channel,
            condition_axes=list(seed.condition_axes),
            geo_text=seed.geo_text,
            safety_notes=seed.safety_notes,
            tagline=seed.tagline,
            aliases=list(seed.aliases),
            guide=guide,
            created_by=author_id,
        )
        session.add(subject)
        await session.flush()
    else:
        subject.name = seed.name
        subject.type = seed.resolved_type()
        subject.primary_channel = seed.channel
        subject.condition_axes = list(seed.condition_axes)
        subject.geo_text = seed.geo_text
        subject.safety_notes = seed.safety_notes
        subject.tagline = seed.tagline
        subject.aliases = list(seed.aliases)
        subject.guide = guide
        if subject.created_by is None:
            subject.created_by = author_id
    await _replace_examples(session, subject, seed)
    return subject


async def _replace_examples(session: AsyncSession, subject: Subject, seed: SubjectSeed) -> None:
    result = await session.execute(select(SubjectExample).where(SubjectExample.subject_id == subject.id))
    existing = {row.name: row for row in result.scalars()}
    seen: set[str] = set()
    for order, example in enumerate(seed.examples):
        if example.name in seen:
            raise SystemExit(f"{seed.slug} 的示例重名：{example.name}")
        seen.add(example.name)
        row = existing.get(example.name)
        if row is None:
            row = SubjectExample(
                subject_id=subject.id,
                name=example.name,
                geo_text=example.geo_text,
                note=example.note,
                sort_order=order,
                verify_status=example.verify_status,
            )
            session.add(row)
        else:
            row.geo_text = example.geo_text
            row.note = example.note
            row.sort_order = order
            row.verify_status = example.verify_status
    for name, row in existing.items():
        if name not in seen:
            await session.delete(row)


async def _ensure_unsorted(session: AsyncSession, author_id) -> None:
    result = await session.execute(select(Subject).where(Subject.slug == UNSORTED_SLUG))
    subject = result.scalar_one_or_none()
    if subject is None:
        session.add(
            Subject(
                slug=UNSORTED_SLUG,
                name="待归类",
                type="scene",
                primary_channel="portrait",
                condition_axes=[],
                tagline="还没挂上题材的投稿。只在审核台可见。",
                aliases=[],
                guide=None,
                safety_notes="审核员必须先改挂到真实题材，才能通过。",
                created_by=author_id,
            )
        )
        return
    subject.name = "待归类"
    subject.tagline = "还没挂上题材的投稿。只在审核台可见。"


async def _prune(session: AsyncSession, keep_slugs: set[str]) -> int:
    keep_slugs = set(keep_slugs)
    keep_slugs.add(UNSORTED_SLUG)
    result = await session.execute(select(Subject))
    removed = 0
    for subject in list(result.scalars()):
        if subject.slug in keep_slugs:
            continue
        note_count = await session.scalar(select(func.count()).select_from(Note).where(Note.subject_id == subject.id))
        if note_count:
            print(f"保留 {subject.slug}：已有 {note_count} 篇笔记，不删除。")
            continue
        await session.execute(delete(SubjectExample).where(SubjectExample.subject_id == subject.id))
        await session.execute(delete(SubjectTag).where(SubjectTag.subject_id == subject.id))
        await session.delete(subject)
        removed += 1
        print(f"已移除不在种子清单里的空题材：{subject.slug}")
    return removed


async def seed(path: Path | None = None, *, prune: bool = False) -> None:
    subject_path = path or DEFAULT_SUBJECTS
    if not subject_path.is_file():
        raise SystemExit(f"找不到种子文件：{subject_path}")
    seeds = load_subject_seeds(subject_path)
    settings = get_settings()
    engine: AsyncEngine = make_engine(settings.database_url)
    await ensure_schema(engine)
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
        await session.flush()
        for item in seeds:
            await _upsert_subject(session, item, author.id)
        await _ensure_unsorted(session, author.id)
        removed = 0
        if prune:
            removed = await _prune(session, {item.slug for item in seeds})
        await session.commit()
    await engine.dispose()
    example_count = sum(len(item.examples) for item in seeds)
    print(f"种子已写入：{len(TAGS)} 个标签，{len(seeds)} 个公开题材，{example_count} 个地点示例，隐藏题材 {UNSORTED_SLUG}。")
    if prune:
        print(f"本次移除空题材 {removed} 个。")
    # 导入时再校验一遍，避免种子和模型漂移。
    SubjectGuide.model_validate(seeds[0].guide.model_dump())


def main() -> None:
    parser = argparse.ArgumentParser(description="导入 SkyTrace 题材种子")
    parser.add_argument("--subjects", default=str(DEFAULT_SUBJECTS), help="题材 JSON 路径")
    parser.add_argument("--prune", action="store_true", help="删除不在 JSON 里、且没有笔记的旧题材")
    args = parser.parse_args()
    asyncio.run(seed(Path(args.subjects), prune=args.prune))


if __name__ == "__main__":
    main()
