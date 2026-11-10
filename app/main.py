import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api.v1 import router as api_router
from app.auth.oauth import reserved_oauth_note
from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.errors import ApiError, error_body
from app.web.routes import router as web_router
from app.web.templating import TEMPLATES

logger = logging.getLogger("skytrace")

STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "UNPROCESSABLE",
    500: "INTERNAL",
}
STATUS_MESSAGES = {
    400: "字段缺失或类型不合法",
    401: "请先登录",
    403: "没有权限",
    404: "资源不存在",
    409: "状态冲突",
    413: "上传内容过大",
    422: "无法处理该请求",
    500: "服务器内部错误",
}
ENGLISH_DETAILS = {"Not Found", "Not Authenticated", "Forbidden", "Unauthorized", "Internal Server Error"}


def _wants_json(request: Request) -> bool:
    return request.url.path.startswith("/api/")


def _html_error(request: Request, status_code: int, message: str):
    user = getattr(request.state, "current_user", None)
    return TEMPLATES.TemplateResponse(
        request,
        "error.html",
        {
            "current_user": user,
            "active": "",
            "status_code": status_code,
            "message": message,
        },
        status_code=status_code,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Path(settings.media_root).mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.oauth_reservation = reserved_oauth_note()
    logger.info("%s", app.state.oauth_reservation)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="SkyTrace", version=__version__, lifespan=lifespan)
    app.include_router(web_router)
    app.include_router(api_router, prefix="/api/v1")

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        if _wants_json(request):
            return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code)
        return _html_error(request, exc.status_code, exc.message)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException):
        code = STATUS_CODES.get(exc.status_code, "INTERNAL" if exc.status_code >= 500 else "VALIDATION_ERROR")
        detail = exc.detail if isinstance(exc.detail, str) else None
        if detail is None or detail in ENGLISH_DETAILS:
            message = STATUS_MESSAGES.get(exc.status_code, "请求失败")
        else:
            message = detail
        if _wants_json(request):
            return JSONResponse(error_body(code, message), status_code=exc.status_code)
        return _html_error(request, exc.status_code, message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        message = "字段缺失或类型不合法"
        if request.url.path == "/login" and not _wants_json(request):
            return TEMPLATES.TemplateResponse(
                request,
                "login.html",
                {
                    "current_user": None,
                    "active": "login",
                    "next": "/",
                    "error": "请填写邮箱和密码",
                },
                status_code=400,
            )
        if _wants_json(request):
            body = error_body("VALIDATION_ERROR", message)
            body["error"]["details"] = [
                {"loc": [str(part) for part in item.get("loc", [])], "msg": item.get("msg", "")}
                for item in exc.errors()
            ]
            return JSONResponse(body, status_code=400)
        return _html_error(request, 400, message)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        logger.exception("未预期错误")
        message = STATUS_MESSAGES[500]
        if _wants_json(request):
            return JSONResponse(error_body("INTERNAL", message), status_code=500)
        return _html_error(request, 500, message)

    return app


app = create_app()
