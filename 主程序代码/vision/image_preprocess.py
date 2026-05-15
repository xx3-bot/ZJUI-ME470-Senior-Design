"""Shared image cleanup helpers for OCR and edge-based detectors."""

from __future__ import annotations

import cv2
import numpy as np


def clean_gray_for_edges(frame: np.ndarray) -> np.ndarray:
    """Return a denoised, contrast-normalized grayscale image for edge logic."""
    if frame is None or frame.size == 0:
        raise ValueError("frame is empty")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame.copy()
    gray = cv2.bilateralFilter(gray, d=5, sigmaColor=35, sigmaSpace=35)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def edge_mask(
    frame: np.ndarray,
    *,
    low_threshold: int = 40,
    high_threshold: int = 120,
    close_kernel: tuple[int, int] = (5, 5),
) -> np.ndarray:
    """Denoise -> grayscale cleanup -> Canny -> morphology close."""
    clean = clean_gray_for_edges(frame)
    edges = cv2.Canny(clean, low_threshold, high_threshold)
    if close_kernel[0] > 1 or close_kernel[1] > 1:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, close_kernel)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)
    return edges


def enhance_for_ocr(frame: np.ndarray) -> np.ndarray:
    """Conservative OCR fallback image.

    The primary OCR path should still use the original color image. This helper
    is meant as a second pass when OCR returns no polygons: mild denoise,
    luminance CLAHE, and a small unsharp mask.
    """
    if frame is None or frame.size == 0:
        raise ValueError("frame is empty")
    if frame.ndim == 2:
        gray = clean_gray_for_edges(frame)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    denoised = cv2.bilateralFilter(frame, d=5, sigmaColor=35, sigmaSpace=35)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    enhanced = cv2.cvtColor(cv2.merge((l_channel, a_channel, b_channel)), cv2.COLOR_LAB2BGR)
    blur = cv2.GaussianBlur(enhanced, (0, 0), sigmaX=1.0)
    return cv2.addWeighted(enhanced, 1.35, blur, -0.35, 0)
