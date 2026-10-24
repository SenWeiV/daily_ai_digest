"""Persistent cache for generated platform backgrounds.

The cache stores provider image bytes, never expiring signed URLs or rendered
screenshots. A slot is stable across digest dates; changing the explicit cache
version or the rendering/model dimensions invalidates it deterministically.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_MIME = {
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/jpeg": b"\xff\xd8\xff",
}


class InvalidCachedImage(ValueError):
    """Raised internally when a cache entry is not a valid supported image."""


@dataclass(frozen=True)
class CachedImage:
    content: bytes
    mime_type: str


def image_mime_type(content: bytes) -> str:
    for mime_type, magic in SUPPORTED_MIME.items():
        if content.startswith(magic):
            return mime_type
    raise InvalidCachedImage("unsupported image signature")


def validate_image_bytes(content: bytes) -> str:
    """Validate both the signature and decodability before cache use."""
    mime_type = image_mime_type(content)
    try:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            image.verify()
    except Exception as exc:  # noqa: BLE001 - cache corruption is a miss
        raise InvalidCachedImage(f"image cannot be decoded: {exc}") from exc
    return mime_type


def _safe_slot(slot: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "_" for char in slot)


class BackgroundCache:
    """Versioned, atomic on-disk cache for stable background slots."""

    def __init__(self, root: str | Path, version: str = "1") -> None:
        self.root = Path(root)
        self.version = version

    def _path(
        self,
        style_key: str,
        slot: str,
        width: int,
        height: int,
        dpr: int,
        model: str,
    ) -> Path:
        identity = json.dumps(
            {
                "version": self.version,
                "style": style_key,
                "slot": slot,
                "width": width,
                "height": height,
                "dpr": dpr,
                "model": model,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(identity).hexdigest()[:24]
        return self.root / self.version / _safe_slot(style_key) / f"{_safe_slot(slot)}-{digest}.img"

    def get(
        self,
        style_key: str,
        slot: str,
        width: int,
        height: int,
        dpr: int,
        model: str,
    ) -> CachedImage | None:
        path = self._path(style_key, slot, width, height, dpr, model)
        try:
            content = path.read_bytes()
        except FileNotFoundError:
            return None
        try:
            mime_type = validate_image_bytes(content)
        except InvalidCachedImage as exc:
            logger.warning("背景缓存损坏，删除并重新生成 [%s]: %s", path, exc)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return None
        return CachedImage(content=content, mime_type=mime_type)

    def put(
        self,
        style_key: str,
        slot: str,
        width: int,
        height: int,
        dpr: int,
        model: str,
        content: bytes,
    ) -> CachedImage:
        mime_type = validate_image_bytes(content)
        path = self._path(style_key, slot, width, height, dpr, model)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return CachedImage(content=content, mime_type=mime_type)


def as_data_url(image: CachedImage) -> str:
    import base64

    return f"data:{image.mime_type};base64,{base64.b64encode(image.content).decode('ascii')}"
