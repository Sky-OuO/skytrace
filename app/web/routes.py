from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.backend import apply_login_cookie, clear_login_cookie
from app.auth.deps import credentials_for, get_database_strategy, get_optional_user, get_user_manager
from app.auth.manager import UserManager
from app.catalog import CHANNELS, CHANNEL_BY_CODE
from app.config import get_settings
from app.db import get_session
from app.errors import ApiError
from app.models import Subject, User
from app.services.storage import resolve_storage_path
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
async def home(request: Request, user: User | None = Depends(get_optional_user)):
    return render(request, "home.html", user, active="home")


@router.get("/partials/channel-counts")
async def channel_counts(request: Request, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Subject.primary_channel, func.count()).group_by(Subject.primary_channel))
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


@router.get("/s/{slug}")
async def subject_page(
    slug: str,
    request: Request,
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Subject).where(Subject.slug == slug))
    subject = result.scalar_one_or_none()
    if subject is None:
        raise ApiError(404, "NOT_FOUND", "对象不存在")
    channel = CHANNEL_BY_CODE.get(subject.primary_channel)
    return render(
        request,
        "subject.html",
        user,
        active=subject.primary_channel,
        subject=subject,
        channel_name=channel["name"] if channel else subject.primary_channel,
        type_name=SUBJECT_TYPE_NAMES.get(subject.type, subject.type),
        axes="、".join(subject.condition_axes or []),
    )


@router.get("/n/{note_id}")
async def note_page(note_id: str, request: Request, user: User | None = Depends(get_optional_user)):
    return render(request, "note.html", user, note_id=note_id)


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

