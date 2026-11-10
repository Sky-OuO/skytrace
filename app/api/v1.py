from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.backend import apply_login_cookie, clear_login_cookie
from app.auth.deps import (
    credentials_for,
    get_database_strategy,
    get_optional_user,
    get_user_manager,
    require_reviewer,
    require_user,
)
from app.auth.manager import UserManager
from app.catalog import CHANNELS, CHANNEL_CODES, FACET_NAMES, FACETS
from app.config import get_settings
from app.db import get_session
from app.domain import can_transition, note_requires_portrait_auth
from app.errors import ApiError
from app.models import Media, Note, ReviewTicket, Subject, Tag, User
from app.schemas import DecideIn, LoginIn, NoteWriteIn
from app.services.storage import preview_url_for, read_upload, store_image

router = APIRouter()


class PageQuery:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, alias="pageSize", ge=1, le=50),
    ) -> None:
        self.page = page
        self.page_size = page_size


def envelope(items: list[Any], total: int, page: PageQuery) -> dict[str, Any]:
    return {
        "items": jsonable_encoder(items),
        "total": total,
        "page": page.page,
        "pageSize": page.page_size,
    }


def subject_payload(subject: Subject) -> dict[str, Any]:
    return {
        "id": subject.id,
        "slug": subject.slug,
        "name": subject.name,
        "type": subject.type,
        "primary_channel": subject.primary_channel,
        "condition_axes": list(subject.condition_axes or []),
        "geo_text": subject.geo_text,
        "safety_notes": subject.safety_notes,
        "guide_summary": subject.guide_summary,
        "cover_media_id": subject.cover_media_id,
        "created_at": subject.created_at,
    }


def user_payload(user: User) -> dict[str, Any]:
    return {"id": user.id, "display_name": user.display_name, "role": user.role}


@router.post("/auth/login", tags=["auth"])
async def login(
    body: LoginIn,
    user_manager: UserManager = Depends(get_user_manager),
    strategy: DatabaseStrategy = Depends(get_database_strategy),
) -> JSONResponse:
    user = await user_manager.authenticate(credentials_for(body.email, body.password))
    if user is None or not user.is_active:
        raise ApiError(401, "UNAUTHENTICATED", "邮箱或密码不正确")
    token = await strategy.write_token(user)
    response = JSONResponse(jsonable_encoder(user_payload(user)))
    apply_login_cookie(response, token)
    return response


@router.post("/auth/logout", tags=["auth"], operation_id="api_logout")
async def logout_api(
    request: Request,
    user: User | None = Depends(get_optional_user),
    strategy: DatabaseStrategy = Depends(get_database_strategy),
) -> JSONResponse:
    token = request.cookies.get(get_settings().session_cookie_name)
    if user is not None and token:
        await strategy.destroy_token(token, user)
    response = JSONResponse({"ok": True})
    clear_login_cookie(response)
    return response


@router.get("/auth/me", tags=["auth"])
async def me(user: User = Depends(require_user)) -> dict[str, Any]:
    return jsonable_encoder(user_payload(user))


@router.get("/vocab", tags=["vocab"])
async def vocab(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    result = await session.execute(select(Tag).order_by(Tag.facet, Tag.slug))
    tags = list(result.scalars())
    return {
        "facets": [{"code": code, "name": name} for code, name in FACETS],
        "tags": [
            {"slug": tag.slug, "name": tag.name, "facet": tag.facet, "facet_name": FACET_NAMES.get(tag.facet, tag.facet)}
            for tag in tags
        ],
    }


@router.get("/channels", tags=["channels"])
async def channels(
    page: PageQuery = Depends(),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await session.execute(select(Subject.primary_channel, func.count()).group_by(Subject.primary_channel))
    counts = {code: count for code, count in result.all()}
    items = [
        {"code": channel["code"], "name": channel["name"], "subject_count": int(counts.get(channel["code"], 0))}
        for channel in CHANNELS
    ]
    start = (page.page - 1) * page.page_size
    return envelope(items[start : start + page.page_size], len(items), page)


@router.get("/subjects", tags=["subjects"])
async def list_subjects(
    channel: str | None = None,
    page: PageQuery = Depends(),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if channel is not None and channel not in CHANNEL_CODES:
        raise ApiError(400, "VALIDATION_ERROR", "未知频道")
    count_stmt = select(func.count()).select_from(Subject)
    list_stmt = select(Subject).order_by(Subject.slug)
    if channel is not None:
        count_stmt = count_stmt.where(Subject.primary_channel == channel)
        list_stmt = list_stmt.where(Subject.primary_channel == channel)
    total = (await session.execute(count_stmt)).scalar_one()
    rows = await session.execute(
        list_stmt.offset((page.page - 1) * page.page_size).limit(page.page_size)
    )
    return envelope([subject_payload(row) for row in rows.scalars()], total, page)


@router.get("/subjects/{slug}", tags=["subjects"])
async def get_subject(slug: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    result = await session.execute(select(Subject).where(Subject.slug == slug))
    subject = result.scalar_one_or_none()
    if subject is None:
        raise ApiError(404, "NOT_FOUND", "对象不存在")
    return jsonable_encoder(subject_payload(subject))


@router.post("/media", tags=["media"])
async def upload_media(
    file: UploadFile = File(...),
    role: str = Form("photo"),
    alt: str | None = Form(None),
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if role not in {"cover", "annotation", "photo"}:
        raise ApiError(400, "VALIDATION_ERROR", "媒体角色不合法")
    if alt is not None and len(alt) > 500:
        raise ApiError(400, "VALIDATION_ERROR", "alt 过长")
    data = await read_upload(file)
    stored = store_image(data)
    media = Media(
        storage_key=stored.storage_key,
        mime=stored.mime,
        byte_size=stored.byte_size,
        width=stored.width,
        height=stored.height,
        role=role,
        alt=alt,
        created_by=user.id,
    )
    session.add(media)
    try:
        await session.flush()
    except Exception:
        stored.path.unlink(missing_ok=True)
        raise
    return {
        "id": str(media.id),
        "storage_key": media.storage_key,
        "preview_url": preview_url_for(media.storage_key),
        "mime": media.mime,
        "byte_size": media.byte_size,
        "width": media.width,
        "height": media.height,
        "role": media.role,
    }


@router.get("/notes/{note_id}", tags=["notes"])
async def get_note(note_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    note = await session.get(Note, note_id)
    if note is None or note.status != "approved":
        raise ApiError(404, "NOT_FOUND", "笔记不存在或尚未公开")
    author = await session.get(User, note.author_id)
    return jsonable_encoder(
        {
            "id": note.id,
            "subject_id": note.subject_id,
            "type": note.type,
            "title": note.title,
            "body": note.body,
            "fields": note.fields,
            "status": note.status,
            "published_at": note.published_at,
            "author": None
            if author is None
            else {"id": author.id, "display_name": author.display_name},
        }
    )


@router.post("/notes", tags=["notes"])
async def create_note(
    body: NoteWriteIn,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del user
    if body.subject_id is None:
        raise ApiError(422, "UNPROCESSABLE", "未选对象")
    subject = await session.get(Subject, body.subject_id)
    if subject is None:
        raise ApiError(404, "NOT_FOUND", "对象不存在")
    raise ApiError(422, "UNPROCESSABLE", "笔记保存将在后续天数开放")


@router.patch("/notes/{note_id}", tags=["notes"])
async def update_note(
    note_id: UUID,
    body: NoteWriteIn,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del body
    note = await session.get(Note, note_id)
    if note is None:
        raise ApiError(404, "NOT_FOUND", "笔记不存在")
    if note.author_id != user.id:
        raise ApiError(403, "FORBIDDEN", "只能修改自己的笔记")
    if note.status == "approved":
        raise ApiError(409, "CONFLICT", "已过审笔记不能直接修改")
    raise ApiError(422, "UNPROCESSABLE", "笔记修改将在后续天数开放")


@router.post("/notes/{note_id}/submit", tags=["notes"])
async def submit_note(
    note_id: UUID,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    note = await session.get(Note, note_id)
    if note is None:
        raise ApiError(404, "NOT_FOUND", "笔记不存在")
    if note.author_id != user.id:
        raise ApiError(403, "FORBIDDEN", "只能提交自己的笔记")
    if not can_transition(note.status, "pending_review"):
        raise ApiError(409, "CONFLICT", "当前状态不能提交")
    subject = await session.get(Subject, note.subject_id)
    channel = subject.primary_channel if subject is not None else ""
    if note_requires_portrait_auth(note.type, channel) and not note.portrait_auth_accepted:
        raise ApiError(422, "UNPROCESSABLE", "人像笔记提交前需要确认肖像授权")
    raise ApiError(422, "UNPROCESSABLE", "提交审核将在后续天数开放")


@router.get("/me/notes", tags=["notes"])
async def my_notes(
    user: User = Depends(require_user),
    page: PageQuery = Depends(),
) -> dict[str, Any]:
    del user
    return envelope([], 0, page)


@router.get("/review/tickets", tags=["review"])
async def list_tickets(
    user: User = Depends(require_reviewer),
    page: PageQuery = Depends(),
) -> dict[str, Any]:
    del user
    return envelope([], 0, page)


@router.post("/review/tickets/{ticket_id}/decide", tags=["review"])
async def decide_ticket(
    ticket_id: UUID,
    body: DecideIn | None = Body(default=None),
    user: User = Depends(require_reviewer),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    del user
    if body is not None and body.decision is not None and body.decision not in {"approved", "rejected"}:
        raise ApiError(400, "VALIDATION_ERROR", "审核决定只能是通过或驳回")
    ticket = await session.get(ReviewTicket, ticket_id)
    if ticket is None:
        raise ApiError(404, "NOT_FOUND", "审核工单不存在")
    raise ApiError(422, "UNPROCESSABLE", "审核决定将在后续天数开放")


@router.get("/search", tags=["search"])
async def search(
    q: str | None = None,
    page: PageQuery = Depends(),
) -> dict[str, Any]:
    del q
    return envelope([], 0, page)


@router.post("/search/parse", tags=["search"])
async def parse_search() -> dict[str, Any]:
    raise ApiError(422, "UNPROCESSABLE", "搜索解析将在后续天数开放")


@router.post("/publish/suggest", tags=["publish"])
async def suggest_publish(user: User = Depends(require_user)) -> dict[str, Any]:
    del user
    raise ApiError(422, "UNPROCESSABLE", "发布助手将在后续天数开放")
