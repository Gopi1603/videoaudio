"""
Watermarking package — audio & video forensic watermark embed / extract.

Provides a unified API used by the media upload/download pipeline:
    embed_watermark(file_path, output_path, payload, media_type) -> dict
    extract_watermark(file_path, media_type, payload_length) -> dict
"""

from app.watermark.audio import embed_audio_watermark, extract_audio_watermark
from app.watermark.video import embed_video_watermark, extract_video_watermark

__all__ = [
    "embed_watermark",
    "extract_watermark",
    "embed_audio_watermark",
    "extract_audio_watermark",
    "embed_video_watermark",
    "extract_video_watermark",
]

AUDIO_EXTENSIONS = {"mp3", "wav", "ogg", "flac", "aac"}
VIDEO_EXTENSIONS = {"mp4", "avi", "mkv", "mov", "webm"}


def _detect_media_type(filepath: str) -> str:
    ext = filepath.rsplit(".", 1)[-1].lower()
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    raise ValueError(f"Unsupported extension: .{ext}")


def embed_watermark(
    src_path: str,
    dst_path: str,
    payload: str,
    media_type: str | None = None,
) -> dict:
    """Embed an invisible watermark carrying *payload* (e.g. user-ID + timestamp).

    Returns a metadata dict with keys like ``watermark_id``, ``snr_db``, etc.
    """
    if media_type is None:
        media_type = _detect_media_type(src_path)

    if media_type == "audio":
        return embed_audio_watermark(src_path, dst_path, payload)
    elif media_type == "video":
        return embed_video_watermark(src_path, dst_path, payload)
    else:
        raise ValueError(f"Unknown media type: {media_type}")


def extract_watermark(
    filepath: str,
    payload_length: int,
    media_type: str | None = None,
) -> dict:
    """Extract the watermark payload from a watermarked file.

    Returns dict with ``payload``, ``match`` (bool), ``bit_error_rate``, etc.
    """
    if media_type is None:
        media_type = _detect_media_type(filepath)

    if media_type == "audio":
        return extract_audio_watermark(filepath, payload_length)
    elif media_type == "video":
        return extract_video_watermark(filepath, payload_length)
    else:
        raise ValueError(f"Unknown media type: {media_type}")
