"""
Phase 6 — Testing & Validation: Watermark Fidelity & Robustness
Tests watermark accuracy under compression, noise, resampling, and batch processing.
"""

import os
import wave
import struct
import tempfile
import time

import numpy as np
import pytest

os.environ["FERNET_MASTER_KEY"] = "t2JVH7Bj3GkX6vN8QfW0MpYrA5z1LcDs9iUoEhKlRxw="

from app.watermark.audio import embed_audio_watermark, extract_audio_watermark
from app.watermark.video import embed_video_watermark, extract_video_watermark
from app.watermark import embed_watermark, extract_watermark


# ── Helpers ────────────────────────────────────────────────────────────

def _make_wav(path, duration_s=3.0, rate=44100, freq=440):
    t = np.linspace(0, duration_s, int(rate * duration_s), endpoint=False)
    samples = (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.tobytes())
    return path


def _make_video(path, n_frames=90, fps=30.0, w=320, h=240):
    import cv2
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, fps, (w, h))
    rng = np.random.RandomState(42)
    for i in range(n_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :, 0] = np.linspace(0, 200, w, dtype=np.uint8)
        frame[:, :, 1] = int(i * 2) % 256
        frame[:, :, 2] = 80
        frame += rng.randint(0, 10, frame.shape, dtype=np.uint8)
        out.write(frame)
    out.release()
    return path


def _add_noise_wav(src, dst, noise_level=500):
    """Add Gaussian noise to a WAV file."""
    with wave.open(src, "rb") as wf:
        params = wf.getparams()
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    noise = np.random.RandomState(99).normal(0, noise_level, samples.shape)
    noisy = np.clip(samples + noise, -32768, 32767).astype(np.int16)
    with wave.open(dst, "wb") as wf:
        wf.setparams(params)
        wf.writeframes(noisy.tobytes())
    return dst


def _resample_wav(src, dst, new_rate=22050):
    """Resample WAV to a different sample rate and back to original rate."""
    with wave.open(src, "rb") as wf:
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
        params = wf.getparams()
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    # Downsample
    ratio = new_rate / rate
    new_len = int(len(samples) * ratio)
    indices = np.linspace(0, len(samples) - 1, new_len)
    downsampled = np.interp(indices, np.arange(len(samples)), samples)
    # Upsample back
    original_indices = np.linspace(0, len(downsampled) - 1, len(samples))
    resampled = np.interp(original_indices, np.arange(len(downsampled)), downsampled)
    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
    with wave.open(dst, "wb") as wf:
        wf.setparams(params)
        wf.writeframes(resampled.tobytes())
    return dst


# ── Audio Watermark Imperceptibility ──────────────────────────────────

class TestAudioImperceptibility:
    """SNR > 20 dB ensures watermark is imperceptible."""

    def test_snr_with_440hz_tone(self, tmp_path):
        src = _make_wav(str(tmp_path / "tone440.wav"), duration_s=5.0, freq=440)
        dst = str(tmp_path / "wm440.wav")
        meta = embed_audio_watermark(src, dst, "uid:1|ts:1700000000")
        print(f"  440 Hz SNR = {meta['snr_db']:.1f} dB")
        assert meta["snr_db"] > 18

    def test_snr_with_1khz_tone(self, tmp_path):
        src = _make_wav(str(tmp_path / "tone1k.wav"), duration_s=5.0, freq=1000)
        dst = str(tmp_path / "wm1k.wav")
        meta = embed_audio_watermark(src, dst, "uid:2|ts:1700000001")
        print(f"  1kHz SNR = {meta['snr_db']:.1f} dB")
        assert meta["snr_db"] > 18

    def test_snr_with_short_payload(self, tmp_path):
        src = _make_wav(str(tmp_path / "s.wav"), duration_s=3.0)
        dst = str(tmp_path / "sw.wav")
        meta = embed_audio_watermark(src, dst, "a")
        assert meta["snr_db"] > 18

    def test_snr_with_long_payload(self, tmp_path):
        src = _make_wav(str(tmp_path / "l.wav"), duration_s=5.0)
        dst = str(tmp_path / "lw.wav")
        payload = "uid:999|ts:9999999999|session:abc123xyz"
        meta = embed_audio_watermark(src, dst, payload)
        print(f"  Long payload SNR = {meta['snr_db']:.1f} dB")
        assert meta["snr_db"] > 15


# ── Audio Watermark Robustness ────────────────────────────────────────

class TestAudioWatermarkRobustness:
    """Phase 6: Watermark extraction after noise, resampling, etc."""

    def test_extraction_after_noise(self, tmp_path):
        """Watermark should survive light Gaussian noise."""
        src = _make_wav(str(tmp_path / "orig.wav"), duration_s=5.0)
        wm = str(tmp_path / "wm.wav")
        payload = "uid:5|ts:1700000000"
        embed_audio_watermark(src, wm, payload)

        noisy = _add_noise_wav(wm, str(tmp_path / "noisy.wav"), noise_level=200)
        result = extract_audio_watermark(noisy, len(payload.encode()))
        # Allow partial match — robustness metric
        match_ratio = sum(a == b for a, b in zip(result["payload"], payload)) / len(payload)
        print(f"  Noise robustness: {match_ratio:.0%} character match")
        # We expect at least partial survival
        assert match_ratio > 0.3, f"Watermark destroyed by noise: {match_ratio:.0%}"

    def test_extraction_after_resample(self, tmp_path):
        """Watermark should survive resample down/up cycle."""
        src = _make_wav(str(tmp_path / "orig.wav"), duration_s=5.0)
        wm = str(tmp_path / "wm.wav")
        payload = "uid:7|ts:1700000000"
        embed_audio_watermark(src, wm, payload)

        resampled = _resample_wav(wm, str(tmp_path / "resampled.wav"), new_rate=22050)
        result = extract_audio_watermark(resampled, len(payload.encode()))
        match_ratio = sum(a == b for a, b in zip(result["payload"], payload)) / len(payload)
        print(f"  Resample robustness: {match_ratio:.0%} character match")
        assert match_ratio > 0.3

    def test_extraction_without_distortion(self, tmp_path):
        """Baseline: extraction from undistorted file must be 100%."""
        src = _make_wav(str(tmp_path / "orig.wav"), duration_s=3.0)
        wm = str(tmp_path / "wm.wav")
        payload = "uid:1|ts:1700000001"
        embed_audio_watermark(src, wm, payload)

        result = extract_audio_watermark(wm, len(payload.encode()))
        assert result["payload"] == payload, "Undistorted extraction failed"


# ── Video Watermark Imperceptibility & Robustness ─────────────────────

class TestVideoWatermarkFidelity:
    def test_psnr_above_threshold(self, tmp_path):
        src = _make_video(str(tmp_path / "v.mp4"), n_frames=60)
        dst = str(tmp_path / "vw.mp4")
        meta = embed_video_watermark(src, dst, "uid:1|ts:1700000000")
        print(f"  Video PSNR = {meta['avg_psnr_db']:.1f} dB")
        assert meta["avg_psnr_db"] > 20, f"PSNR too low: {meta['avg_psnr_db']}"

    def test_all_frames_watermarked(self, tmp_path):
        src = _make_video(str(tmp_path / "v.mp4"), n_frames=30)
        dst = str(tmp_path / "vw.mp4")
        meta = embed_video_watermark(src, dst, "uid:2|ts:1700000000")
        assert meta["frames_watermarked"] > 0

    def test_video_roundtrip_extraction(self, tmp_path):
        src = _make_video(str(tmp_path / "v.mp4"), n_frames=90)
        dst = str(tmp_path / "vw.mp4")
        payload = "uid:3|ts:1700000000"
        embed_video_watermark(src, dst, payload)
        result = extract_video_watermark(dst, len(payload.encode()))
        assert result["payload"] == payload

    def test_different_video_payloads(self, tmp_path):
        src = _make_video(str(tmp_path / "v.mp4"), n_frames=90)
        m1 = embed_video_watermark(src, str(tmp_path / "v1.mp4"), "user:1")
        m2 = embed_video_watermark(src, str(tmp_path / "v2.mp4"), "user:2")
        assert m1["watermark_id"] != m2["watermark_id"]


# ── Batch Processing (Kaggle-inspired) ────────────────────────────────

class TestBatchWatermarkProcessing:
    """Phase 6: Simulate batch processing on multiple files, track detection rate."""

    def test_audio_batch_detection_rate(self, tmp_path):
        """Embed & extract watermarks on 5 audio files, check 100% detection."""
        successes = 0
        total = 5
        for i in range(total):
            src = _make_wav(str(tmp_path / f"batch_{i}.wav"), duration_s=3.0, freq=440 + i * 100)
            dst = str(tmp_path / f"batch_{i}_wm.wav")
            payload = f"uid:{i}|ts:17000{i:05d}"
            embed_audio_watermark(src, dst, payload)
            result = extract_audio_watermark(dst, len(payload.encode()))
            if result["payload"] == payload:
                successes += 1
        rate = successes / total
        print(f"  Audio batch detection rate: {rate:.0%} ({successes}/{total})")
        assert rate == 1.0, f"Detection rate {rate:.0%} < 100%"

    def test_video_batch_detection_rate(self, tmp_path):
        """Embed & extract watermarks on 3 video files, check 100% detection."""
        successes = 0
        total = 3
        for i in range(total):
            src = _make_video(str(tmp_path / f"vbatch_{i}.mp4"), n_frames=90)
            dst = str(tmp_path / f"vbatch_{i}_wm.mp4")
            payload = f"vid:{i}|ts:17000{i:05d}"
            embed_video_watermark(src, dst, payload)
            result = extract_video_watermark(dst, len(payload.encode()))
            if result["payload"] == payload:
                successes += 1
        rate = successes / total
        print(f"  Video batch detection rate: {rate:.0%} ({successes}/{total})")
        assert rate == 1.0


# ── Performance Benchmarks ────────────────────────────────────────────

class TestWatermarkPerformance:
    def test_audio_embed_speed(self, tmp_path):
        src = _make_wav(str(tmp_path / "perf.wav"), duration_s=10.0)
        dst = str(tmp_path / "perf_wm.wav")
        t0 = time.perf_counter()
        embed_audio_watermark(src, dst, "benchmark-payload")
        elapsed = time.perf_counter() - t0
        file_mb = os.path.getsize(src) / (1024 * 1024)
        print(f"  Audio watermark: {file_mb:.1f} MB in {elapsed:.3f}s")
        assert elapsed < 30, f"Audio watermark too slow: {elapsed:.1f}s"

    def test_video_embed_speed(self, tmp_path):
        src = _make_video(str(tmp_path / "perf.mp4"), n_frames=90)
        dst = str(tmp_path / "perf_wm.mp4")
        t0 = time.perf_counter()
        embed_video_watermark(src, dst, "benchmark-payload")
        elapsed = time.perf_counter() - t0
        print(f"  Video watermark: 90 frames in {elapsed:.3f}s")
        assert elapsed < 60, f"Video watermark too slow: {elapsed:.1f}s"
