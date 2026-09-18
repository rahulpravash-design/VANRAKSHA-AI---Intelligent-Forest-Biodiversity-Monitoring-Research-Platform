"""Media storage with server-side validation.

Uploads are never trusted on the basis of their filename or the ``Content-Type``
header the client sent.  Every file is:

1. size-checked while streaming, so an oversized upload is rejected before it is
   held in memory in full;
2. decoded and verified by the codec itself (Pillow for images, the audio
   decoder for recordings), which is what actually establishes the media type;
3. stored under a name derived from its SHA-256 digest, which removes path
   traversal and filename collisions as a class of problem and makes duplicate
   uploads detectable.

The local backend is the default.  ``STORAGE_BACKEND=s3`` switches to object
storage, which is what a production deployment should use — large media does not
belong on the API server's disk.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import UploadTooLargeError, ValidationError
from app.models.enums import MediaKind

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024

IMAGE_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
#: The canonical suffix for each detected format. The stored filename is built
#: from what the decoder actually found, not from the client's filename — a JPEG
#: uploaded as ``photo.png`` would otherwise be served with a PNG content type by
#: any static file server that guesses from the extension.
EXTENSION_BY_FORMAT = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "WAV": ".wav",
    "FLAC": ".flac",
    "OGG": ".ogg",
    "MP3": ".mp3",
    "AIFF": ".aiff",
}

AUDIO_MIME_BY_FORMAT = {
    "WAV": "audio/wav",
    "FLAC": "audio/flac",
    "OGG": "audio/ogg",
    "MP3": "audio/mpeg",
    "AIFF": "audio/aiff",
}


@dataclass(frozen=True)
class StoredMedia:
    kind: MediaKind
    storage_key: str
    public_url: str
    mime_type: str
    size_bytes: int
    checksum: str
    original_filename: str | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    sample_rate: int | None = None


async def read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an upload, aborting as soon as it exceeds ``max_bytes``."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLargeError(
                f"File exceeds the {max_bytes // (1024 * 1024)} MB limit."
            )
        chunks.append(chunk)
    if total == 0:
        raise ValidationError("Uploaded file is empty.")
    return b"".join(chunks)


def _check_extension(filename: str | None, allowed: list[str], label: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed:
        raise ValidationError(
            f"{label} must be one of: {', '.join(allowed)} (received '{suffix or 'none'}')."
        )
    return suffix


class StorageBackend:
    """Interface implemented by the local and S3 backends."""

    def save(self, data: bytes, key: str, mime_type: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def delete(self, key: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def public_url(self, key: str) -> str:  # pragma: no cover
        raise NotImplementedError


class LocalStorage(StorageBackend):
    def __init__(self, root: Path | None = None, base_url: str | None = None) -> None:
        self.root = root or settings.storage_root
        self.base_url = (base_url or settings.storage_public_base_url).rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        # Defence in depth: keys are derived from digests, but never let a key
        # resolve outside the storage root.
        if not str(candidate).startswith(str(self.root.resolve())):
            raise ValidationError("Invalid storage key.")
        return candidate

    def save(self, data: bytes, key: str, mime_type: str) -> str:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():  # content-addressed: identical bytes need one copy
            path.write_bytes(data)
        return self.public_url(key)

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.exists():
            path.unlink()

    def public_url(self, key: str) -> str:
        return f"{self.base_url}/{key}"


class S3Storage(StorageBackend):  # pragma: no cover - requires boto3 + credentials
    """Object storage for production deployments."""

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise ValidationError(
                "STORAGE_BACKEND=s3 requires boto3; install it or use the local backend."
            ) from exc
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
        )
        self._bucket = settings.s3_bucket

    def save(self, data: bytes, key: str, mime_type: str) -> str:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=mime_type
        )
        return self.public_url(key)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def public_url(self, key: str) -> str:
        base = settings.storage_public_base_url.rstrip("/")
        return f"{base}/{key}"


_backend: StorageBackend | None = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = S3Storage() if settings.storage_backend.lower() == "s3" else LocalStorage()
    return _backend


def reset_storage() -> None:
    """Drop the cached backend — used by the test suite."""
    global _backend
    _backend = None


def _key_for(kind: MediaKind, checksum: str, suffix: str) -> str:
    stamp = datetime.now(UTC)
    folder = {
        MediaKind.IMAGE: "images",
        MediaKind.AUDIO: "audio",
        MediaKind.SPECTROGRAM: "spectrograms",
        MediaKind.DOCUMENT: "documents",
    }[kind]
    # Date-partitioned, content-addressed: cheap to browse, safe to name.
    return f"{folder}/{stamp:%Y/%m}/{checksum[:16]}{suffix}"


def store_image(data: bytes, original_filename: str | None) -> StoredMedia:
    """Validate and store a photograph."""
    from ai.preprocessing.image import ImageValidationError, inspect_image

    _check_extension(original_filename, settings.allowed_image_extensions, "Image")
    if len(data) > settings.max_image_bytes:
        raise UploadTooLargeError(
            f"Image exceeds the {settings.max_image_upload_mb} MB limit."
        )
    try:
        info = inspect_image(data)
    except ImageValidationError as exc:
        raise ValidationError(str(exc)) from exc

    mime_type = IMAGE_MIME_BY_FORMAT.get(info.format)
    if mime_type is None:
        raise ValidationError(
            f"Image format '{info.format}' is not accepted; use JPEG, PNG or WebP."
        )
    checksum = hashlib.sha256(data).hexdigest()
    key = _key_for(MediaKind.IMAGE, checksum, EXTENSION_BY_FORMAT[info.format])
    url = get_storage().save(data, key, mime_type)
    return StoredMedia(
        kind=MediaKind.IMAGE,
        storage_key=key,
        public_url=url,
        mime_type=mime_type,
        size_bytes=len(data),
        checksum=checksum,
        original_filename=original_filename,
        width=info.width,
        height=info.height,
    )


def store_audio(data: bytes, original_filename: str | None) -> StoredMedia:
    """Validate and store a field recording."""
    from ai.preprocessing.audio import AudioValidationError, decode_audio

    _check_extension(original_filename, settings.allowed_audio_extensions, "Audio")
    if len(data) > settings.max_audio_bytes:
        raise UploadTooLargeError(
            f"Recording exceeds the {settings.max_audio_upload_mb} MB limit."
        )
    try:
        decoded = decode_audio(data, filename=original_filename)
    except AudioValidationError as exc:
        raise ValidationError(str(exc)) from exc

    mime_type = AUDIO_MIME_BY_FORMAT.get(decoded.source_format, "application/octet-stream")
    suffix = EXTENSION_BY_FORMAT.get(
        decoded.source_format, Path(original_filename or "").suffix.lower() or ".bin"
    )
    checksum = hashlib.sha256(data).hexdigest()
    key = _key_for(MediaKind.AUDIO, checksum, suffix)
    url = get_storage().save(data, key, mime_type)
    return StoredMedia(
        kind=MediaKind.AUDIO,
        storage_key=key,
        public_url=url,
        mime_type=mime_type,
        size_bytes=len(data),
        checksum=checksum,
        original_filename=original_filename,
        duration_seconds=round(decoded.duration_seconds, 3),
        sample_rate=decoded.sample_rate,
    )


def store_spectrogram(audio_data: bytes, original_filename: str | None) -> StoredMedia | None:
    """Render and store a spectrogram PNG beside a recording.

    Best-effort: a failure here must never fail the observation upload, because
    the spectrogram is a convenience for the reviewer, not primary data.
    """
    from ai.preprocessing.audio import decode_audio, write_spectrogram_png

    try:
        decoded = decode_audio(audio_data, filename=original_filename)
        checksum = hashlib.sha256(audio_data).hexdigest()
        key = _key_for(MediaKind.SPECTROGRAM, checksum, ".png")
        backend = get_storage()
        if isinstance(backend, LocalStorage):
            destination = backend._path_for(key)
            write_spectrogram_png(decoded, destination)
            png = destination.read_bytes()
            url = backend.public_url(key)
        else:  # pragma: no cover - object storage path
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".png") as handle:
                write_spectrogram_png(decoded, handle.name)
                png = Path(handle.name).read_bytes()
            url = backend.save(png, key, "image/png")
        return StoredMedia(
            kind=MediaKind.SPECTROGRAM,
            storage_key=key,
            public_url=url,
            mime_type="image/png",
            size_bytes=len(png),
            checksum=hashlib.sha256(png).hexdigest(),
            original_filename=None,
        )
    except Exception:
        logger.warning("could not render a spectrogram for the upload", exc_info=True)
        return None
