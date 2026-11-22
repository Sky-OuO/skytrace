import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.domain import GUIDE_KEYS, UNSORTED_SLUG, SubjectGuide
from app.models import Subject, SubjectExample
from app.seed import seed

ROOT = Path(__file__).resolve().parents[1]


def test_seed_file_has_no_forbidden_word_and_window_examples_are_not_topics():
    raw = json.loads((ROOT / "seeds" / "subjects.json").read_text(encoding="utf-8"))
    blob = json.dumps(raw, ensure_ascii=False)
    assert "私房" not in blob
    assert "思想开源" not in blob
    slugs = {item["slug"] for item in raw}
    assert "cafe-window" not in slugs
    assert UNSORTED_SLUG not in slugs
    assert 30 <= len(raw) <= 50
    assert len(raw) == 37
    window = next(item for item in raw if item["slug"] == "window-light-portrait")
    example_names = {item["name"] for item in window["examples"]}
    assert {"咖啡馆窗边", "西餐厅靠窗座", "火车/高铁车窗"} <= example_names
    assert "高铁窗边" in window["aliases"]
    clouds = next(item for item in raw if item["slug"] == "sea-of-clouds-sunrise")
    assert "黄山" in {item["name"] for item in clouds["examples"]}
    for name in example_names:
        assert name not in {item["name"] for item in raw}
    for item in raw:
        guide = SubjectGuide.model_validate(item["guide"])
        for key in GUIDE_KEYS:
            lines = getattr(guide, key)
            assert 2 <= len(lines) <= 4


async def test_seed_is_idempotent_and_hides_unsorted(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def counts():
        async with factory() as session:
            subjects = await session.scalar(select(func.count()).select_from(Subject))
            examples = await session.scalar(select(func.count()).select_from(SubjectExample))
            window = (
                await session.execute(select(Subject).where(Subject.slug == "window-light-portrait"))
            ).scalar_one()
            return subjects, examples, list(window.aliases)

    before = await counts()
    await seed(prune=True)
    after = await counts()
    assert before[0] == after[0]
    assert before[1] == after[1]
    assert "咖啡馆窗边" in after[2]
    async with factory() as session:
        unsorted = (
            await session.execute(select(Subject).where(Subject.slug == UNSORTED_SLUG))
        ).scalar_one()
        assert unsorted.guide is None
        listed = (
            await session.execute(select(SubjectExample).where(SubjectExample.name == "西餐厅靠窗座"))
        ).scalar_one()
        owner = await session.get(Subject, listed.subject_id)
        assert owner.slug == "window-light-portrait"
        assert "人像笔记须声明展示授权" in (owner.notices or [])
