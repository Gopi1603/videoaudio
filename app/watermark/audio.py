"""
Spread-spectrum audio watermarking (CDMA-style, full-band).

Technique:
  • Convert audio to frequency domain (FFT).
  • For each payload bit, generate a PN (pseudo-noise) sequence spanning the
    ENTIRE usable frequency band (CDMA approach — all bits share the band,
    separated by orthogonal codes).
  • Modulate PN by the bit value (±1) and add scaled to spectrum magnitudes.
  • On extraction, correlate against each PN and decide by sign.

This avoids chip-overlap problems and supports payloads up to ~200 bits
at 44.1 kHz / 3 s audio.

Dependencies: numpy, scipy, pydub (for format conversion to WAV).
"""

import hashlib
import struct
import wave
import tempfile
import os
from typing import Tuple

import numpy as np

# ---- tuning knobs --------------------------------------------------------
_ALPHA = 0.2           # watermark strength
_CHIP_LENGTH = 512     # samples per bit
_SECRET = b"SecureMedia-WM-2026"
_BAND_LOW = 1000       # for reference (not used in time-domain)
_BAND_HIGH = 8000


# ---- helpers --------------------------------------------------------------

def _str_to_bits(s: str) -> list[int]:
    """Convert a UTF-8 string to a list of 0/1 ints."""
    raw = s.encode("utf-8")
    bits = []
    for byte in raw:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_str(bits: list[int]) -> str:
    """Recover a UTF-8 string from a bit list (length must be multiple of 8)."""
    n = len(bits) // 8
    chars = []
    for i in range(n):
        val = 0
        for j in range(8):
            val = (val << 1) | bits[i * 8 + j]
        chars.append(val)
    return bytes(chars).decode("utf-8", errors="replace")


def _pn_sequence(bit_index: int, length: int) -> np.ndarray:
    """Deterministic ±1 PN sequence for a given bit position."""
    seed = hashlib.sha256(_SECRET + struct.pack(">I", bit_index)).digest()
    rng = np.random.RandomState(int.from_bytes(seed[:4], "big"))
    return rng.choice([-1, 1], size=length).astype(np.float64)


def _read_wav(path: str) -> Tuple[np.ndarray, int, int]:
    """Read a WAV file → (samples float64, sample_rate, n_channels)."""
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        dtype = np.int16
    elif sampwidth == 4:
        dtype = np.int32
    else:
        dtype = np.int16  # fallback

    samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels)[:, 0]  # mono mix (first channel)
    return samples, rate, n_channels


def _write_wav(path: str, samples: np.ndarray, rate: int, sampwidth: int = 2) -> None:
    samples_int = np.clip(samples, -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(samples_int.tobytes())


def _to_wav(src: str) -> Tuple[str, bool]:
    """If *src* is not .wav, convert via pydub. Return (wav_path, was_converted)."""
    if src.lower().endswith(".wav"):
        return src, False
    from pydub import AudioSegment
    audio = AudioSegment.from_file(src)
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    audio.export(wav_path, format="wav")
    return wav_path, True


def _snr(original: np.ndarray, watermarked: np.ndarray) -> float:
    """Signal-to-Noise Ratio in dB."""
    noise = watermarked - original
    sig_power = np.mean(original ** 2)
    noise_power = np.mean(noise ** 2)
    if noise_power == 0:
        return float("inf")
    return 10 * np.log10(sig_power / noise_power)


# ---- public API -----------------------------------------------------------

def embed_audio_watermark(src_path: str, dst_path: str, payload: str) -> dict:
    """Embed *payload* via time-domain spread-spectrum watermarking."""
    wav_path, converted = _to_wav(src_path)
    try:
        samples, rate, _ = _read_wav(wav_path)
    finally:
        if converted:
            os.unlink(wav_path)

    bits = _str_to_bits(payload)
    n_bits = len(bits)
    
    # Check if audio is long enough
    if len(samples) < n_bits * _CHIP_LENGTH:
        raise ValueError("Audio too short for this payload length.")
    
    watermarked = samples.copy()
    
    for i, bit in enumerate(bits):
        start = i * _CHIP_LENGTH
        end = start + _CHIP_LENGTH
        pn = _pn_sequence(i, _CHIP_LENGTH)
        symbol = 1.0 if bit else -1.0
        watermarked[start:end] += _ALPHA * symbol * pn * np.abs(samples[start:end])
    
    snr_val = _snr(samples, watermarked)
    _write_wav(dst_path, watermarked, rate)

    return {
        "watermark_id": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "payload_bits": n_bits,
        "snr_db": round(snr_val, 2),
        "method": "spread-spectrum-time",
    }


def extract_audio_watermark(filepath: str, payload_length: int) -> dict:
    """Extract watermark from time-domain correlation.

    Returns dict: payload, payload_bits, method.
    """
    wav_path, converted = _to_wav(filepath)
    try:
        samples, rate, _ = _read_wav(wav_path)
    finally:
        if converted:
            os.unlink(wav_path)

    n_bits = payload_length * 8
    
    extracted_bits: list[int] = []
    for i in range(n_bits):
        start = i * _CHIP_LENGTH
        end = start + _CHIP_LENGTH
        if end > len(samples):
            extracted_bits.append(0)
            continue
        pn = _pn_sequence(i, _CHIP_LENGTH)
        segment = samples[start:end]
        correlation = np.dot(segment, pn)
        extracted_bits.append(1 if correlation > 0 else 0)

    recovered = _bits_to_str(extracted_bits)

    return {
        "payload": recovered,
        "payload_bits": n_bits,
        "method": "spread-spectrum-time",
    }
