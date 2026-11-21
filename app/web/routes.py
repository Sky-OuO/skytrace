from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.backend import apply_login_cookie, clear_login_cookie
from app.auth.deps import credentials_for, get_database_strategy, get_optional_user, get_user_manager
from app.auth.manager import UserManager
from app.catalog import CHANNELS, CHANNEL_BY_CODE
from app.domain import UNSORTED_SLUG
from app.config import get_settings
from app.db import get_session
from app.errors import ApiError
from app.models import Subject, User
from app.services.storage import resolve_storage_path
from app.services.feed import load_feed
from app.services.topics import approved_note_and_subject, public_subject, topic_context
from app.web.templating import TEMPLATES
from fastapi_users.authentication.strategy.db import DatabaseStrategy

router = APIRouter(include_in_schema=False)

SUBJECT_TYPE_NAMES = {"location": "地点", "scene": "场景", "theme": "主题"}


def safe_next(value: str | None) -> str:
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value


def render(
    request: Request,
    name: str,
    user: User | None,
    status_code: int = 200,
    **extra: object,
):
    active = extra.pop("active", "")
    return TEMPLATES.TemplateResponse(
        request,
        name,
        {"current_user": user, "active": active, "channels": CHANNELS, **extra},
        status_code=status_code,
    )


@router.get("/")
async def home(
    request: Request,
    channel: str | None = None,
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
):
    page = await load_feed(session, channel=channel, limit=6)
    return render(
        request,
        "home.html",
        user,
        active="home",
        cards=page["items"],
        next_cursor=page["next_cursor"],
        feed_channel=channel or "",
    )


@router.get("/partials/feed")
async def feed_partial(
    request: Request,
    cursor: str | None = None,
    channel: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    page = await load_feed(session, channel=channel or None, cursor=cursor, limit=6)
    return TEMPLATES.TemplateResponse(
        request,
        "partials/feed_more.html",
        {
            "cards": page["items"],
            "next_cursor": page["next_cursor"],
            "feed_channel": channel or "",
        },
    )


@router.get("/partials/channel-counts")
async def channel_counts(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Subject.primary_channel, func.count())
        .where(Subject.slug != UNSORTED_SLUG)
        .group_by(Subject.primary_channel)
    )
    counts = {code: count for code, count in result.all()}
    items = [
        {"name": channel["name"], "subject_count": int(counts.get(channel["code"], 0))}
        for channel in CHANNELS
    ]
    return TEMPLATES.TemplateResponse(request, "partials/channel_counts.html", {"channels": items})


@router.get("/c/{channel}")
async def channel_page(channel: str, request: Request, user: User | None = Depends(get_optional_user)):
    spec = CHANNEL_BY_CODE.get(channel)
    if spec is None:
        raise ApiError(404, "NOT_FOUND", "没有这个频道")
    return render(request, "channel.html", user, active=channel, channel=spec)


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ApiError(404, "NOT_FOUND", "笔记不存在或尚未公开") from exc


@router.get("/s/{slug}")
async def subject_page(
    slug: str,
    request: Request,
    work: str | None = None,
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
):
    subject = await public_subject(session, slug)
    if subject is None:
        raise ApiError(404, "NOT_FOUND", "对象不存在")
    highlight = None
    if work:
        found = await approved_note_and_subject(session, _parse_uuid(work))
        if found is None:
            raise ApiError(404, "NOT_FOUND", "笔记不存在或尚未公开")
        note, owner = found
        if owner.slug != subject.slug:
            return RedirectResponse(f"/s/{owner.slug}?work={note.id}", status_code=302)
        highlight_id = note.id
    else:
        highlight_id = None
    channel = CHANNEL_BY_CODE.get(subject.primary_channel)
    context = await topic_context(session, subject)
    if highlight_id is not None:
        for section in context["sections"]:
            for item in section["notes"]:
                if item["id"] == highlight_id:
                    highlight = item
                    break
    return render(
        request,
        "subject.html",
        user,
        active=subject.primary_channel,
        subject=subject,
        channel_name=channel["name"] if channel else subject.primary_channel,
        type_name=SUBJECT_TYPE_NAMES.get(subject.type, subject.type),
        axes="、".join(subject.condition_axes or []),
        highlight=highlight,
        **context,
    )


@router.get("/w/{work_id}")
async def work_redirect(work_id: str, session: AsyncSession = Depends(get_session)):
    found = await approved_note_and_subject(session, _parse_uuid(work_id))
    if found is None:
        raise ApiError(404, "NOT_FOUND", "笔记不存在或尚未公开")
    note, owner = found
    return RedirectResponse(f"/s/{owner.slug}?work={note.id}", status_code=302)


@router.get("/n/{note_id}")
async def note_page(note_id: str, session: AsyncSession = Depends(get_session)):
    """旧的笔记地址。作品不再单独开页，转到题材页并高亮。"""
    return await work_redirect(note_id, session)


@router.get("/publish")
async def publish(request: Request, user: User | None = Depends(get_optional_user)):
    if user is None:
        return RedirectResponse("/login?next=/publish", status_code=303)
    return render(request, "publish.html", user, active="publish")


@router.get("/search")
async def search(request: Request, q: str | None = None, user: User | None = Depends(get_optional_user)):
    return render(request, "search.html", user, active="search", q=q or "")


@router.get("/review")
async def review(request: Request, user: User | None = Depends(get_optional_user)):
    if user is None or user.role != "reviewer":
        raise ApiError(403, "FORBIDDEN", "只有审核员可以进入审核台。")
    return render(request, "review.html", user, active="review")


@router.get("/ideas")
async def ideas(request: Request, user: User | None = Depends(get_optional_user)):
    return render(request, "ideas.html", user, active="ideas")


@router.get("/login")
async def login_form(request: Request, next: str = "/", user: User | None = Depends(get_optional_user)):
    target = safe_next(next)
    if user is not None:
        return RedirectResponse(target, status_code=303)
    return render(request, "login.html", user, active="login", next=target, error=None)


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    user_manager: UserManager = Depends(get_user_manager),
    strategy: DatabaseStrategy = Depends(get_database_strategy),
):
    target = safe_next(next)
    user = await user_manager.authenticate(credentials_for(email, password))
    if user is None or not user.is_active:
        return render(
            request,
            "login.html",
            None,
            status_code=401,
            active="login",
            next=target,
            error="邮箱或密码不正确",
        )
    token = await strategy.write_token(user)
    response = RedirectResponse(target, status_code=303)
    apply_login_cookie(response, token)
    return response


@router.api_route("/logout", methods=["GET", "POST"])
async def logout_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
    strategy: DatabaseStrategy = Depends(get_database_strategy),
):
    token = request.cookies.get(get_settings().session_cookie_name)
    if user is not None and token:
        await strategy.destroy_token(token, user)
    response = RedirectResponse("/", status_code=303)
    clear_login_cookie(response)
    return response


@router.get("/media/{storage_key:path}")
async def read_media(storage_key: str):
    import mimetypes

    path = resolve_storage_path(storage_key)
    if not path.is_file():
        raise ApiError(404, "NOT_FOUND", "媒体不存在")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)

