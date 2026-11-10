import io
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import get_settings
from app.errors import ApiError

IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
    "GIF": ("image/gif", "gif"),
}


@dataclass
class StoredImage:
    storage_key: str
    mime: str
    byte_size: int
    width: int
    height: int
    path: Path


def resolve_storage_path(storage_key: str, root: Path | None = None) -> Path:
    if not storage_key or "\x00" in storage_key:
        raise ApiError(400, "VALIDATION_ERROR", "非法存储路径")
    raw = Path(storage_key)
    if raw.is_absolute() or ".." in raw.parts:
        raise ApiError(400, "VALIDATION_ERROR", "非法存储路径")
    base = (root or Path(get_settings().media_root)).resolve()
    candidate = (base / raw).resolve()
    if candidate != base and base not in candidate.parents:
        raise ApiError(400, "VALIDATION_ERROR", "非法存储路径")
    return candidate


def preview_url_for(storage_key: str) -> str:
    base = get_settings().media_preview_base_url.rstrip("/")
    return f"{base}/{storage_key}"


async def read_upload(upload: UploadFile, limit: int | None = None) -> bytes:
    max_bytes = get_settings().media_max_bytes if limit is None else limit
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise ApiError(413, "PAYLOAD_TOO_LARGE", "图片超过大小上限")
        chunks.append(chunk)
    if size == 0:
        raise ApiError(400, "VALIDATION_ERROR", "没有读到图片内容")
    return b"".join(chunks)


def store_image(data: bytes, root: Path | None = None) -> StoredImage:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            fmt = image.format
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise ApiError(400, "VALIDATION_ERROR", "只接受 JPEG、PNG、WEBP 或 GIF 图片") from exc
    if fmt not in IMAGE_FORMATS:
        raise ApiError(400, "VALIDATION_ERROR", "只接受 JPEG、PNG、WEBP 或 GIF 图片")
    mime, ext = IMAGE_FORMATS[fmt]
    storage_key = f"uploads/{uuid4().hex}.{ext}"
    path = resolve_storage_path(storage_key, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return StoredImage(
        storage_key=storage_key,
        mime=mime,
        byte_size=len(data),
        width=width,
        height=height,
        path=path,
    )
