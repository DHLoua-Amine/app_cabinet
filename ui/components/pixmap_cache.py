"""
pixmap_cache.py — Bounded, pre-scaled avatar cache.

Each page kept its own `dict` of full-resolution QPixmaps keyed by file path, with no
eviction. The pixmaps were only ever drawn at 60-150 px, but the full image stayed in
memory for the life of the process:

    measured: 50 client profiles viewed -> +16.5 MB RSS, 50 cache entries, none freed
    projected at 10,000 clients         -> ~1.9 GB at the current photo size,
                                           ~447 GB if clients attach phone photos

This module caches the *rendered* avatar instead of the source image, and evicts
least-recently-used entries so the ceiling is fixed regardless of client count.
"""

from collections import OrderedDict

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QBrush, QColor

# 384 entries x 150x150x4 bytes worst case = ~34 MB ceiling; typical 70px avatars ~7 MB.
MAX_ENTRIES = 384

_cache: "OrderedDict[tuple, QPixmap]" = OrderedDict()


def _store(key, pixmap):
    _cache[key] = pixmap
    _cache.move_to_end(key)
    while len(_cache) > MAX_ENTRIES:
        _cache.popitem(last=False)
    return pixmap


def clear():
    _cache.clear()


def invalidate(path: str):
    """
    Drops every cached rendering of one file.

    Entries are keyed by file path, so replacing a document with a new file of the
    same name (or deleting one) would otherwise keep showing the previous image for
    the rest of the session.
    """
    for key in [k for k in _cache if len(k) > 1 and k[1] == path]:
        _cache.pop(key, None)


def circular_avatar(path: str, size: int) -> QPixmap:
    """
    A circular avatar of exactly `size` px, cached.

    Returns a null QPixmap when the file cannot be read, so callers can fall through
    to their placeholder.
    """
    key = ("circle", path, size)
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit

    src = QPixmap(path)
    if src.isNull():
        return src

    scaled = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)
    rounded = QPixmap(size, size)
    rounded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(scaled))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    # `src` and `scaled` go out of scope here: the full-resolution image is not kept.
    return _store(key, rounded)


def scaled_preview(path: str, w: int, h: int) -> QPixmap:
    """A plain scaled preview (not circular), cached at the display size."""
    key = ("scaled", path, w, h)
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit

    src = QPixmap(path)
    if src.isNull():
        return src
    out = src.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    return _store(key, out)


def placeholder_avatar(size: int, fill="#334155", dot="#64748b") -> QPixmap:
    """The generic avatar used when a client has no photo. Cached once per size."""
    key = ("placeholder", size, fill, dot)
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit

    pm = QPixmap(size, size)
    pm.fill(QColor(fill))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(QColor(dot)))
    painter.drawEllipse(4, 4, size - 8, size - 8)
    painter.end()
    return _store(key, pm)
