from __future__ import annotations

"""内容签名校验与同源文件响应的最小安全契约。

上传方提供的扩展名和 ``Content-Type`` 都只能作为声明，不能作为文件
类型的事实来源。这里先校验内容签名，再校验扩展名和声明 MIME 一致；
调用方只保存/返回校验后的 canonical MIME。
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
import warnings

from PIL import Image, UnidentifiedImageError


class UnsafeFileError(ValueError):
    """文件类型、签名或声明不符合允许契约。"""


@dataclass(frozen=True, slots=True)
class ValidatedFile:
    filename: str
    mime: str
    family: str


_RASTER_FORMATS: dict[str, tuple[str, frozenset[str]]] = {
    "PNG": ("image/png", frozenset({".png"})),
    "JPEG": ("image/jpeg", frozenset({".jpg", ".jpeg"})),
    "GIF": ("image/gif", frozenset({".gif"})),
    "WEBP": ("image/webp", frozenset({".webp"})),
    "BMP": ("image/bmp", frozenset({".bmp"})),
    "TIFF": ("image/tiff", frozenset({".tif", ".tiff"})),
}
_MIME_ALIASES: dict[str, frozenset[str]] = {
    "image/png": frozenset({"image/png"}),
    "image/jpeg": frozenset({"image/jpeg", "image/jpg", "image/pjpeg"}),
    "image/gif": frozenset({"image/gif"}),
    "image/webp": frozenset({"image/webp"}),
    "image/bmp": frozenset({"image/bmp", "image/x-ms-bmp"}),
    "image/tiff": frozenset({"image/tiff", "image/x-tiff"}),
    "application/pdf": frozenset({"application/pdf"}),
    "application/msword": frozenset({"application/msword"}),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": frozenset(
        {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    ),
}


def _safe_filename(value: str) -> str:
    filename = PurePath(str(value or "document").replace("\\", "/")).name
    filename = filename.replace("\x00", "").replace("\r", "").replace("\n", "").strip()[:500]
    if not filename or filename in {".", ".."}:
        raise UnsafeFileError("文件名无效")
    return filename


def _declared_mime_matches(canonical: str, declared: str) -> bool:
    value = str(declared or "").split(";", 1)[0].strip().lower()
    return value in _MIME_ALIASES.get(canonical, frozenset())


def _verify_raster(content: bytes) -> tuple[str, frozenset[str]]:
    # Pillow 的 decoder 校验放在显式 magic 之后，避免只依赖扩展名或 MIME。
    signatures = (
        content.startswith(b"\x89PNG\r\n\x1a\n"),
        content.startswith(b"\xff\xd8\xff"),
        content.startswith((b"GIF87a", b"GIF89a")),
        len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP",
        content.startswith(b"BM"),
        content.startswith((b"II*\x00", b"MM\x00*")),
    )
    if not any(signatures):
        raise UnsafeFileError("图片文件签名无效")
    try:
        # Pillow normally emits DecompressionBombWarning instead of failing.
        # Treat it as a hard validation error: compressed image dimensions can
        # otherwise create a browser/Worker memory DoS despite the byte limit.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image_format = str(image.format or "").upper()
                image.verify()
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise UnsafeFileError("图片内容无法通过完整性校验") from exc
    contract = _RASTER_FORMATS.get(image_format)
    if not contract:
        raise UnsafeFileError("图片格式不在允许列表中")
    return contract


def validate_raster_image(
    *,
    filename: str,
    declared_mime: str,
    content: bytes,
    allow_generic_mime: bool = False,
) -> ValidatedFile:
    safe_name = _safe_filename(filename)
    payload = bytes(content or b"")
    if not payload:
        raise UnsafeFileError("图片不能为空")
    canonical_mime, extensions = _verify_raster(payload)
    suffix = PurePath(safe_name).suffix.lower()
    if suffix not in extensions:
        raise UnsafeFileError("图片扩展名与内容签名不一致")
    declared = str(declared_mime or "").split(";", 1)[0].strip().lower()
    if not _declared_mime_matches(canonical_mime, declared) and not (
        allow_generic_mime and declared == "application/octet-stream"
    ):
        raise UnsafeFileError("图片 MIME 与内容签名不一致")
    return ValidatedFile(filename=safe_name, mime=canonical_mime, family="raster")
