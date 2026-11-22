"""记一笔的页面。表单只展开当前笔记类型。"""

from uuid import UUID

from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import TAGS
from app.domain import NOTE_TYPE_NAMES, NOTE_TYPES, UNSORTED_SLUG, note_requires_portrait_auth
from app.errors import ApiError
from app.models import Media, SubjectExample, User
from app.services.publishing import (
    create_note,
    default_tag_slugs,
    find_topics,
    replace_tags,
    subject_by_slug,
    submit_note,
)
from app.services.storage import read_upload, store_image
from app.web.templating import TEMPLATES

FIELD_INPUTS = {
    "spot": (
        ("arrival", "怎么到达", False),
        ("time_window", "时间窗口", False),
        ("focal_length", "焦段", False),
        ("exposure", "曝光", False),
        ("common_failures", "常见失败", False),
    ),
    "pre": (
        ("tickets_permits", "预约与许可", False),
        ("transport_arrival", "交通", False),
        ("season_window", "季节窗口", False),
        ("gear_advice", "器材", False),
        ("safety_tips", "安全", False),
        ("common_failures", "常见失败", False),
    ),
    "post": (
        ("white_balance_exposure", "白平衡与曝光", True),
        ("crop_advice", "裁切", False),
        ("material_color", "材质与色彩", False),
        ("common_failures", "常见失败", False),
    ),
    "lighting": (
        ("key_light", "主光", True),
        ("fill_light", "辅光", False),
        ("rim_light", "轮廓光", False),
        ("ambient_light", "环境光", False),
        ("common_failures", "常见失败", False),
    ),
    "posing": (
        ("body_orientation", "身体朝向", True),
        ("contact_points", "接触点", True),
        ("light_relationship", "和光线的关系", True),
        ("common_failures", "常见失败", False),
    ),
}


def _checked_slug(form_value: str | None, query_subject: str | None) -> str:
    return (form_value or query_subject or "").strip()


async def _examples(session: AsyncSession, subject_id) -> list[SubjectExample]:
    from sqlalchemy import select

    rows = await session.execute(
        select(SubjectExample).where(SubjectExample.subject_id == subject_id).order_by(SubjectExample.sort_order)
    )
    return list(rows.scalars())


async def render_publish(
    request: Request,
    user: User,
    session: AsyncSession,
    *,
    subject_slug: str = "",
    note_type: str = "finished",
    error: str | None = None,
    body: str = "",
    status_code: int = 200,
):
    subject = await subject_by_slug(session, subject_slug) if subject_slug else None
    if subject is not None and subject.slug == UNSORTED_SLUG:
        subject_for_tags = subject
    else:
        subject_for_tags = subject if subject is not None and subject.slug != "" else None
    topics = await find_topics(session, "", selected=subject_slug or None)
    examples = await _examples(session, subject.id) if subject is not None and subject.slug != UNSORTED_SLUG else []
    needs_auth = True
    if subject is not None and subject.slug != UNSORTED_SLUG:
        needs_auth = note_requires_portrait_auth(note_type, subject.primary_channel)
    tag_slugs = default_tag_slugs(subject_for_tags) if subject_for_tags is not None else ()
    return TEMPLATES.TemplateResponse(
        request,
        "publish.html",
        {
            "current_user": user,
            "active": "publish",
            "channels": [],
            "topics": topics,
            "subject_slug": subject_slug,
            "subject": subject,
            "examples": examples,
            "note_type": note_type if note_type in NOTE_TYPES else "finished",
            "note_types": [(code, NOTE_TYPE_NAMES[code]) for code in NOTE_TYPES],
            "field_inputs": FIELD_INPUTS.get(note_type, ()),
            "needs_auth": needs_auth,
            "tags": [(slug, name) for _facet, slug, name in TAGS],
            "selected_tags": set(tag_slugs),
            "error": error,
            "body": body,
            "unsorted_slug": UNSORTED_SLUG,
            "selected": subject_slug,
            "oob": False,
        },
        status_code=status_code,
    )


async def topic_picker(request: Request, session: AsyncSession, q: str, selected: str):
    topics = await find_topics(session, q, selected=selected or None)
    subject = await subject_by_slug(session, selected) if selected else None
    examples = []
    if subject is not None and subject.slug != UNSORTED_SLUG:
        examples = await _examples(session, subject.id)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/topic_picker.html",
        {
            "topics": topics,
            "selected": selected,
            "examples": examples,
            "unsorted_slug": UNSORTED_SLUG,
            "oob": True,
        },
    )


async def publish_fields(request: Request, session: AsyncSession, note_type: str, subject_slug: str):
    if note_type not in NOTE_TYPES:
        note_type = "finished"
    subject = await subject_by_slug(session, subject_slug) if subject_slug else None
    needs_auth = True
    if subject is not None and subject.slug != UNSORTED_SLUG:
        needs_auth = note_requires_portrait_auth(note_type, subject.primary_channel)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/publish_fields.html",
        {
            "note_type": note_type,
            "field_inputs": FIELD_INPUTS.get(note_type, ()),
            "needs_auth": needs_auth,
            "body": "",
        },
    )


async def accept_publish(
    request: Request,
    user: User,
    session: AsyncSession,
):
    form = await request.form()
    subject_slug = str(form.get("subject_slug") or "")
    note_type = str(form.get("type") or "finished")
    body = str(form.get("body") or "")
    action = str(form.get("action") or "submit")
    portrait_auth = form.get("portrait_auth") in {"on", "true", "1"}
    title = str(form.get("title") or "")
    example_raw = str(form.get("example_id") or "")
    try:
        subject = await subject_by_slug(session, subject_slug)
        if subject is None:
            raise ApiError(422, "UNPROCESSABLE", "请选择题材，或选待归类")
        example_id = UUID(example_raw) if example_raw else None
        fields = {}
        for key, _label, _required in FIELD_INPUTS.get(note_type, ()):
            value = str(form.get(f"field_{key}") or "").strip()
            if value:
                fields[key] = value
        note = await create_note(
            session,
            user,
            subject_id=subject.id,
            note_type=note_type,
            title=title,
            body=body,
            fields=fields,
            portrait_auth_accepted=portrait_auth,
            example_id=example_id,
        )
        upload = form.get("image")
        if upload is not None and getattr(upload, "filename", ""):
            stored = store_image(await read_upload(upload))
            session.add(
                Media(
                    storage_key=stored.storage_key,
                    mime=stored.mime,
                    byte_size=stored.byte_size,
                    width=stored.width,
                    height=stored.height,
                    role="photo",
                    alt=f"{note.title}，示例图",
                    note_id=note.id,
                    subject_id=subject.id,
                    created_by=user.id,
                )
            )
            await session.flush()
        tag_values = form.getlist("tags") if hasattr(form, "getlist") else []
        if not tag_values:
            tag_values = list(default_tag_slugs(subject))
        await replace_tags(session, note, [str(item) for item in tag_values])
        if action == "draft":
            return RedirectResponse("/me?notice=draft", status_code=303)
        await submit_note(session, user, note.id)
    except ApiError as exc:
        await session.rollback()
        return await render_publish(
            request,
            user,
            session,
            subject_slug=subject_slug,
            note_type=note_type,
            error=exc.message,
            body=body,
            status_code=exc.status_code,
        )
    return RedirectResponse("/me?notice=pending", status_code=303)
