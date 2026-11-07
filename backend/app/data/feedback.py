"""User feedback: optional message, optional category, optional screenshot. Mobile and time are saved automatically."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import List, Optional, Tuple

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from ..db import feedback

CATEGORIES = ("Bug", "Idea", "Other")
MAX_MESSAGE = 5000
MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
# Only raster images, identified by their first bytes (not the file name). SVG is excluded: it can carry scripts.
_MAGIC = [(b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif")]


def image_type(data: bytes) -> Optional[str]:
    for magic, kind in _MAGIC:
        if data.startswith(magic):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class FeedbackItem:
    id: int
    mobile: str
    created_at: str
    category: Optional[str]
    message: Optional[str]
    has_screenshot: bool


class FeedbackStore:
    def __init__(self, engine: Engine):
        self._engine = engine

    def add(self, mobile: str, message: Optional[str], category: Optional[str], screenshot: Optional[bytes]) -> int:
        message = (message or "").strip() or None
        category = (category or "").strip() or None
        if category is not None and category not in CATEGORIES:
            raise ValueError(f"Category must be one of {', '.join(CATEGORIES)}")
        if message and len(message) > MAX_MESSAGE:
            raise ValueError(f"Message is too long (max {MAX_MESSAGE} characters)")
        kind = None
        if screenshot:
            if len(screenshot) > MAX_SCREENSHOT_BYTES:
                raise ValueError("Screenshot is too large (max 5 MB)")
            kind = image_type(screenshot)
            if kind is None:
                raise ValueError("Screenshot must be a PNG, JPEG, GIF or WebP image")
        else:
            screenshot = None
        if not message and not screenshot:
            raise ValueError("Write a message or attach a screenshot")
        with self._engine.begin() as conn:
            res = conn.execute(insert(feedback).values(mobile=mobile, created_at=datetime.now(UTC), category=category,
                                                       message=message, screenshot=screenshot, screenshot_type=kind))
            return int(res.inserted_primary_key[0])

    def list(self) -> List[FeedbackItem]:
        q = select(feedback.c.id, feedback.c.mobile, feedback.c.created_at, feedback.c.category, feedback.c.message,
                   feedback.c.screenshot_type).order_by(feedback.c.id.desc())
        with self._engine.connect() as conn:
            return [FeedbackItem(i, m, t.isoformat() if t else "", c, msg, st is not None) for i, m, t, c, msg, st in conn.execute(q)]

    def screenshot(self, item_id: int) -> Optional[Tuple[bytes, str]]:
        q = select(feedback.c.screenshot, feedback.c.screenshot_type).where(feedback.c.id == item_id)
        with self._engine.connect() as conn:
            row = conn.execute(q).first()
        return (bytes(row[0]), row[1]) if row and row[0] else None
