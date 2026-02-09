"""
DWT-based video watermarking (frame-level).

Technique:
  • Extract key-frames from the video (every Nth frame).
  • For each key-frame, apply a 2-D Haar DWT (Discrete Wavelet Transform).
  • Embed payload bits into the LL (low-frequency) sub-band coefficients
    using a PN (pseudo-noise) spread-spectrum approach — same idea as audio
    but operating on 2-D image data.
  • Reconstruct frames and write the watermarked video.

On extraction:
  • Read key-frames, DWT, correlate against PN sequences, majority-vote
    across frames for each bit.

Dependencies: numpy, cv2 (OpenCV), scipy (for pywt-like Haar DWT).
"""

import hashlib
import struct
import os
import tempfile
from typing import Tuple, List

import numpy as np
import cv2

# ---- tuning knobs --------------------------------------------------------
_ALPHA = 0.02           # watermark strength per DWT coefficient
_SECRET = b"SecureMedia-VWM-2026"
_KEYFRAME_INTERVAL = 30  # embed in every Nth frame


# ---- helpers --------------------------------------------------------------

def _str_to_bits(s: str) -> list[int]:
    raw = s.encode("utf-8")
    bits = []
    for byte in raw:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_str(bits: list[int]) -> str:
    n = len(bits) // 8
    chars = []
    for i in range(n):
        val = 0
        for j in range(8):
            val = (val << 1) | bits[i * 8 + j]
        chars.append(val)
    return bytes(chars).decode("utf-8", errors="replace")


def _pn_sequence(bit_index: int, length: int) -> np.ndarray:
    seed = hashlib.sha256(_SECRET + struct.pack(">I", bit_index)).digest()
    rng = np.random.RandomState(int.from_bytes(seed[:4], "big"))
    return rng.choice([-1, 1], size=length).astype(np.float64)


def _haar_dwt2(img: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Simple 2-D Haar DWT → (LL, LH, HL, HH)."""
    h, w = img.shape[:2]
    h2, w2 = h // 2, w // 2
    img = img[:h2 * 2, :w2 * 2].astype(np.float64)

    # Row-wise
    low = (img[:, 0::2] + img[:, 1::2]) / 2.0
    high = (img[:, 0::2] - img[:, 1::2]) / 2.0

    # Column-wise on low
    LL = (low[0::2, :] + low[1::2, :]) / 2.0
    LH = (low[0::2, :] - low[1::2, :]) / 2.0

    # Column-wise on high
    HL = (high[0::2, :] + high[1::2, :]) / 2.0
    HH = (high[0::2, :] - high[1::2, :]) / 2.0

    return LL, LH, HL, HH


def _haar_idwt2(LL: np.ndarray, LH: np.ndarray, HL: np.ndarray, HH: np.ndarray) -> np.ndarray:
    """Inverse 2-D Haar DWT."""
    h2, w2 = LL.shape[:2]
    h, w = h2 * 2, w2 * 2

    # Reconstruct low and high from columns
    low = np.zeros((h, w2), dtype=np.float64)
    low[0::2, :] = (LL + LH)
    low[1::2, :] = (LL - LH)

    high = np.zeros((h, w2), dtype=np.float64)
    high[0::2, :] = (HL + HH)
    high[1::2, :] = (HL - HH)

    # Reconstruct from rows
    img = np.zeros((h, w), dtype=np.float64)
    img[:, 0::2] = (low + high)
    img[:, 1::2] = (low - high)

    return img


def _embed_bits_in_ll(ll: np.ndarray, bits: list[int]) -> np.ndarray:
    """Spread-spectrum embed bits into the LL sub-band (CDMA full-band)."""
    flat = ll.flatten().copy()
    n = len(flat)
    
    if n < len(bits):
        raise ValueError("LL sub-band too small for payload")
    
    mag = np.abs(flat)
    for i, bit in enumerate(bits):
        pn = _pn_sequence(i, n)
        symbol = 1.0 if bit else -1.0
        flat += _ALPHA * symbol * pn * mag
    
    return flat.reshape(ll.shape)


def _extract_bits_from_ll(ll: np.ndarray, n_bits: int) -> list[int]:
    flat = ll.flatten()
    n = len(flat)
    bits = []
    for i in range(n_bits):
        pn = _pn_sequence(i, n)
        corr = np.dot(flat, pn)
        bits.append(1 if corr > 0 else 0)
    return bits


def _psnr(original: np.ndarray, modified: np.ndarray) -> float:
    mse = np.mean((original.astype(np.float64) - modified.astype(np.float64)) ** 2)
    if mse == 0:
        return float("inf")
    return 10 * np.log10(255.0 ** 2 / mse)


# ---- public API -----------------------------------------------------------

def embed_video_watermark(src_path: str, dst_path: str, payload: str) -> dict:
    """Embed *payload* into video frames via DWT spread-spectrum.

    Writes watermarked video to *dst_path*.
    Returns metadata dict.
    """
    bits = _str_to_bits(payload)

    cap = cv2.VideoCapture(src_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {src_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")

    out = cv2.VideoWriter(dst_path, fourcc, fps, (width, height))
    frame_idx = 0
    psnr_values = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % _KEYFRAME_INTERVAL == 0:
            # Convert to grayscale for DWT, embed, merge back
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float64)
            LL, LH, HL, HH = _haar_dwt2(gray)

            if LL.size >= len(bits):
                LL_wm = _embed_bits_in_ll(LL, bits)
                wm_gray = _haar_idwt2(LL_wm, LH, HL, HH)

                # Blend watermark into luminance channel (YCrCb)
                ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb).astype(np.float64)
                orig_y = ycrcb[:, :, 0].copy()

                # Resize wm_gray to match (DWT may truncate odd dimensions)
                h_wm, w_wm = wm_gray.shape
                ycrcb[:h_wm, :w_wm, 0] = wm_gray
                ycrcb = np.clip(ycrcb, 0, 255)

                frame_out = cv2.cvtColor(ycrcb.astype(np.uint8), cv2.COLOR_YCrCb2BGR)
                psnr_values.append(_psnr(frame, frame_out))
                frame = frame_out

        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()

    avg_psnr = float(np.mean(psnr_values)) if psnr_values else float("inf")
    return {
        "watermark_id": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "payload_bits": len(bits),
        "frames_watermarked": len(psnr_values),
        "total_frames": frame_idx,
        "avg_psnr_db": round(avg_psnr, 2),
        "method": "dwt-spread-spectrum",
    }


def extract_video_watermark(filepath: str, payload_length: int) -> dict:
    """Extract watermark from key-frames via DWT correlation + majority vote.

    *payload_length*: number of **bytes** in original payload.
    """
    n_bits = payload_length * 8

    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {filepath}")

    frame_idx = 0
    vote_sums = np.zeros(n_bits, dtype=np.float64)
    n_votes = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % _KEYFRAME_INTERVAL == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float64)
            LL, _, _, _ = _haar_dwt2(gray)

            if LL.size >= n_bits:
                bits = _extract_bits_from_ll(LL, n_bits)
                # convert 0/1 → -1/+1 for voting
                vote_sums += np.array([1 if b else -1 for b in bits], dtype=np.float64)
                n_votes += 1

        frame_idx += 1

    cap.release()

    extracted_bits = [1 if v > 0 else 0 for v in vote_sums]
    recovered = _bits_to_str(extracted_bits)

    return {
        "payload": recovered,
        "payload_bits": n_bits,
        "frames_analyzed": n_votes,
        "method": "dwt-spread-spectrum",
    }
