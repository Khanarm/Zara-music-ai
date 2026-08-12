# music/search.py

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    video_id: Optional[str] = None
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    source: str = "youtube"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "video_id": self.video_id,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


def _duration_seconds(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None
    return None


class YouTubeSearcher:
    """YouTube search layer based on the reference project's API flow."""

    _url_re = re.compile(r"(?:youtube\.com|youtu\.be)", re.I)

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        query = str(query or "").strip()
        if not query:
            return []
        limit = max(1, min(int(limit), 10))
        try:
            from youtubesearchpython.__future__ import VideosSearch
        except ImportError:
            logger.error("youtubesearchpython is not installed")
            return []

        try:
            search = VideosSearch(query, limit=limit)
            payload = await search.next()
            rows = payload.get("result", []) if isinstance(payload, dict) else []
            results: list[SearchResult] = []
            for row in rows:
                url = row.get("link") or row.get("url")
                if not url:
                    video_id = row.get("id")
                    if video_id:
                        url = f"https://www.youtube.com/watch?v={video_id}"
                if not url:
                    continue
                thumbs = row.get("thumbnails") or []
                thumbnail = thumbs[0].get("url") if thumbs and isinstance(thumbs[0], dict) else None
                results.append(
                    SearchResult(
                        title=str(row.get("title") or "Unknown Track"),
                        url=url,
                        video_id=row.get("id"),
                        duration=_duration_seconds(row.get("duration")),
                        thumbnail=thumbnail.split("?")[0] if thumbnail else None,
                        metadata={"raw": row},
                    )
                )
            return results
        except Exception:
            logger.exception("YouTube search failed for %r", query)
            return []

    async def first(self, query: str) -> Optional[SearchResult]:
        results = await self.search(query, 1)
        return results[0] if results else None

    async def resolve(self, url_or_query: str) -> Optional[SearchResult]:
        value = str(url_or_query or "").strip()
        if not value:
            return None
        if self._url_re.search(value):
            try:
                from youtubesearchpython.__future__ import VideosSearch
                search = VideosSearch(value, limit=1)
                payload = await search.next()
                rows = payload.get("result", []) if isinstance(payload, dict) else []
                if rows:
                    row = rows[0]
                    url = row.get("link") or value
                    thumbs = row.get("thumbnails") or []
                    thumbnail = thumbs[0].get("url") if thumbs else None
                    return SearchResult(
                        title=str(row.get("title") or value),
                        url=url,
                        video_id=row.get("id"),
                        duration=_duration_seconds(row.get("duration")),
                        thumbnail=thumbnail.split("?")[0] if thumbnail else None,
                        metadata={"raw": row},
                    )
            except Exception:
                logger.exception("YouTube URL resolve failed")
        return await self.first(value)


_searcher: Optional[YouTubeSearcher] = None


def get_searcher() -> YouTubeSearcher:
    global _searcher
    if _searcher is None:
        _searcher = YouTubeSearcher()
    return _searcher


def reset_searcher() -> None:
    global _searcher
    _searcher = None


async def search_tracks(query: str, limit: int = 5) -> list[SearchResult]:
    return await get_searcher().search(query, limit)


async def search_track(query: str) -> Optional[SearchResult]:
    return await get_searcher().first(query)


__all__ = ["SearchResult", "YouTubeSearcher", "get_searcher", "reset_searcher", "search_tracks", "search_track"]
