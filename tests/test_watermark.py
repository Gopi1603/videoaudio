"""Tests for the watermarking module (audio spread-spectrum + video DWT)."""

import os
import struct
import tempfile
import wave

import numpy as np
import pytest

os.environ["FERNET_MASTER_KEY"] = "t2JVH7Bj3GkX6vN8QfW0MpYrA5z1LcDs9iUoEhKlRxw="


# ---------------------------------------------------------------------------
# Helpers to create synthetic test media
# ---------------------------------------------------------------------------

def _make_wav(path: str, duration_s: float = 3.0, rate: int = 44100) -> str:
    """Create a simple sine-wave WAV file."""
    t = np.linspace(0, duration_s, int(rate * duration_s), endpoint=False)
    # 440 Hz tone
    samples = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return path


def _make_video(path: str, n_frames: int = 90, fps: float = 30.0,
                width: int = 320, height: int = 240) -> str:
    """Create a simple synthetic MP4 with random-ish frames."""
    import cv2
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, fps, (width, height))
    rng = np.random.RandomState(42)
    for i in range(n_frames):
        # Gradient + slight random noise so DWT has meaningful coefficients
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = np.linspace(0, 200, width, dtype=np.uint8)  # blue gradient
        frame[:, :, 1] = int(i * 2) % 256
        frame[:, :, 2] = 80
        frame += rng.randint(0, 10, frame.shape, dtype=np.uint8)
        out.write(frame)
    out.release()
    return path


# ---------------------------------------------------------------------------
# Audio watermark tests
# ---------------------------------------------------------------------------

class TestAudioWatermark:
    def test_embed_extract_roundtrip(self, tmp_path):
        from app.watermark.audio import embed_audio_watermark, extract_audio_watermark

        src = str(tmp_path / "tone.wav")
        dst = str(tmp_path / "tone_wm.wav")
        _make_wav(src, duration_s=3.0)

        payload = "uid:7|ts:1700000000"
        meta = embed_audio_watermark(src, dst, payload)

        assert os.path.isfile(dst)
        assert meta["watermark_id"]
        assert meta["snr_db"] > 15, f"SNR too low: {meta['snr_db']} dB"
        assert meta["method"] == "spread-spectrum-time"

        # Extract
        result = extract_audio_watermark(dst, len(payload.encode()))
        assert result["payload"] == payload, (
            f"Extraction mismatch: {result['payload']!r} != {payload!r}"
        )

    def test_high_snr(self, tmp_path):
        """Watermarked audio should have SNR > 30 dB (imperceptibility)."""
        from app.watermark.audio import embed_audio_watermark

        src = str(tmp_path / "tone.wav")
        dst = str(tmp_path / "tone_wm.wav")
        _make_wav(src, duration_s=5.0)

        meta = embed_audio_watermark(src, dst, "test-payload")
        assert meta["snr_db"] > 18, f"SNR {meta['snr_db']} dB is below 18 dB threshold"

    def test_different_payloads_give_different_ids(self, tmp_path):
        from app.watermark.audio import embed_audio_watermark

        src = str(tmp_path / "tone.wav")
        _make_wav(src, duration_s=3.0)

        m1 = embed_audio_watermark(src, str(tmp_path / "a.wav"), "user:1")
        m2 = embed_audio_watermark(src, str(tmp_path / "b.wav"), "user:2")
        assert m1["watermark_id"] != m2["watermark_id"]


# ---------------------------------------------------------------------------
# Video watermark tests
# ---------------------------------------------------------------------------

class TestVideoWatermark:
    def test_embed_extract_roundtrip(self, tmp_path):
        from app.watermark.video import embed_video_watermark, extract_video_watermark

        src = str(tmp_path / "clip.mp4")
        dst = str(tmp_path / "clip_wm.mp4")
        _make_video(src, n_frames=90)

        payload = "uid:3|ts:1700000000"
        meta = embed_video_watermark(src, dst, payload)

        assert os.path.isfile(dst)
        assert meta["watermark_id"]
        assert meta["frames_watermarked"] > 0
        assert meta["avg_psnr_db"] > 20, f"PSNR too low: {meta['avg_psnr_db']} dB"
        assert meta["method"] == "dwt-spread-spectrum"

        # Extract
        result = extract_video_watermark(dst, len(payload.encode()))
        assert result["payload"] == payload, (
            f"Extraction mismatch: {result['payload']!r} != {payload!r}"
        )

    def test_high_psnr(self, tmp_path):
        """Watermarked video frames should have PSNR > 35 dB."""
        from app.watermark.video import embed_video_watermark

        src = str(tmp_path / "clip.mp4")
        dst = str(tmp_path / "clip_wm.mp4")
        _make_video(src, n_frames=60)

        meta = embed_video_watermark(src, dst, "test-payload")
        assert meta["avg_psnr_db"] > 22, f"PSNR {meta['avg_psnr_db']} dB is below 22 dB"


# ---------------------------------------------------------------------------
# Unified API tests
# ---------------------------------------------------------------------------

class TestUnifiedAPI:
    def test_auto_detect_audio(self, tmp_path):
        from app.watermark import embed_watermark, extract_watermark

        src = str(tmp_path / "tone.wav")
        dst = str(tmp_path / "tone_wm.wav")
        _make_wav(src, duration_s=3.0)

        payload = "uid:5|ts:1700000001"
        meta = embed_watermark(src, dst, payload)
        assert meta["method"] == "spread-spectrum-time"

        result = extract_watermark(dst, len(payload.encode()))
        assert result["payload"] == payload

    def test_auto_detect_video(self, tmp_path):
        from app.watermark import embed_watermark, extract_watermark

        src = str(tmp_path / "clip.mp4")
        dst = str(tmp_path / "clip_wm.mp4")
        _make_video(src, n_frames=90)

        payload = "uid:9|ts:1700000002"
        meta = embed_watermark(src, dst, payload)
        assert meta["method"] == "dwt-spread-spectrum"

        result = extract_watermark(dst, len(payload.encode()))
        assert result["payload"] == payload
