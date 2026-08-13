import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# SEARCH CACHE
# ============================================================

_CACHE_TTL = 300  # 5 minutes
_CACHE_MAX = 100

_search_cache: dict[tuple[str, int], tuple[float, list["SearchResult"]]] = {}
_pending_searches: dict[tuple[str, int], asyncio.Task] = {}


# ============================================================
# SEARCH RESULT
# ============================================================

@dataclass(slots=True)
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


# ============================================================
# HELPERS
# ============================================================

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
            return (
                int(parts[0]) * 3600
                + int(parts[1]) * 60
                + int(parts[2])
            )

    except (ValueError, TypeError):
        return None

    return None


def _clean_query(query: str) -> str:
    return " ".join(str(query or "").strip().split())


def _clean_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None

    url = str(url).strip()

    # Remove tracking parameters from normal YouTube URLs.
    if "youtube.com/watch" in url and "?" in url:
        match = re.search(r"[?&]v=([^&]+)", url)

        if match:
            return f"https://www.youtube.com/watch?v={match.group(1)}"

    return url


def _extract_thumbnail(row: dict[str, Any]) -> Optional[str]:
    thumbs = row.get("thumbnails") or []

    if not isinstance(thumbs, list):
        return None

    for thumb in thumbs:
        if isinstance(thumb, dict):
            url = thumb.get("url")

            if url:
                return str(url).split("?")[0]

    return None


# ============================================================
# YOUTUBE SEARCHER
# ============================================================

class YouTubeSearcher:
    """
    Fast YouTube search layer.

    Features:
    - Async search
    - Short-term result cache
    - Duplicate request protection
    - Lightweight result metadata
    - URL resolving
    """

    _url_re = re.compile(
        r"(?:https?://)?(?:www\.)?"
        r"(?:youtube\.com|youtu\.be)",
        re.I,
    )

    def __init__(self) -> None:
        self._VideosSearch = None

    # --------------------------------------------------------
    # Lazy import
    # --------------------------------------------------------

    def _get_search_class(self):
        if self._VideosSearch is None:
            try:
                from youtubesearchpython.__future__ import VideosSearch

                self._VideosSearch = VideosSearch

            except ImportError:
                logger.error(
                    "youtubesearchpython is not installed"
                )
                return None

        return self._VideosSearch

    # --------------------------------------------------------
    # Cache
    # --------------------------------------------------------

    def _cache_get(
        self,
        query: str,
        limit: int,
    ) -> Optional[list[SearchResult]]:

        key = (query.lower(), limit)

        cached = _search_cache.get(key)

        if not cached:
            return None

        timestamp, results = cached

        if time.monotonic() - timestamp > _CACHE_TTL:
            _search_cache.pop(key, None)
            return None

        return list(results)

    def _cache_set(
        self,
        query: str,
        limit: int,
        results: list[SearchResult],
    ) -> None:

        key = (query.lower(), limit)

        _search_cache[key] = (
            time.monotonic(),
            list(results),
        )

        # Keep cache small.
        if len(_search_cache) > _CACHE_MAX:
            oldest_key = min(
                _search_cache,
                key=lambda k: _search_cache[k][0],
            )

            _search_cache.pop(oldest_key, None)

    # --------------------------------------------------------
    # Parse result
    # --------------------------------------------------------

    @staticmethod
    def _parse_row(row: dict[str, Any]) -> Optional[SearchResult]:

        video_id = row.get("id")

        url = (
            row.get("link")
            or row.get("url")
        )

        if not url and video_id:
            url = (
                f"https://www.youtube.com/watch?v={video_id}"
            )

        if not url:
            return None

        url = _clean_url(url)

        if not url:
            return None

        return SearchResult(
            title=str(
                row.get("title")
                or "Unknown Track"
            ),
            url=url,
            video_id=video_id,
            duration=_duration_seconds(
                row.get("duration")
            ),
            thumbnail=_extract_thumbnail(row),

            # IMPORTANT:
            # Don't keep the complete raw YouTube response.
            metadata={
                "author": (
                    row.get("channel", {}).get("name")
                    if isinstance(row.get("channel"), dict)
                    else None
                )
            },
        )

    # --------------------------------------------------------
    # Actual API search
    # --------------------------------------------------------

    async def _perform_search(
        self,
        query: str,
        limit: int,
    ) -> list[SearchResult]:

        VideosSearch = self._get_search_class()

        if VideosSearch is None:
            return []

        try:
            search = VideosSearch(
                query,
                limit=limit,
            )

            payload = await search.next()

            rows = (
                payload.get("result", [])
                if isinstance(payload, dict)
                else []
            )

            results: list[SearchResult] = []

            for row in rows:

                if not isinstance(row, dict):
                    continue

                result = self._parse_row(row)

                if result:
                    results.append(result)

            return results

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "YouTube search failed for %r",
                query,
            )
            return []

    # --------------------------------------------------------
    # Public search
    # --------------------------------------------------------

    async def search(
        self,
        query: str,
        limit: int = 5,
    ) -> list[SearchResult]:

        query = _clean_query(query)

        if not query:
            return []

        limit = max(
            1,
            min(int(limit), 10),
        )

        # ----------------------------------------------------
        # CACHE
        # ----------------------------------------------------

        cached = self._cache_get(
            query,
            limit,
        )

        if cached is not None:
            return cached

        key = (
            query.lower(),
            limit,
        )

        # ----------------------------------------------------
        # DUPLICATE REQUEST PROTECTION
        # ----------------------------------------------------
        #
        # If 5 users request the same song at almost
        # exactly the same time, only ONE YouTube search
        # is performed.
        #

        existing = _pending_searches.get(key)

        if existing is not None:

            try:
                results = await existing
                return list(results)

            except asyncio.CancelledError:
                raise

            except Exception:
                return []

        task = asyncio.create_task(
            self._perform_search(
                query,
                limit,
            )
        )

        _pending_searches[key] = task

        try:
            results = await task

            self._cache_set(
                query,
                limit,
                results,
            )

            return list(results)

        finally:
            _pending_searches.pop(
                key,
                None,
            )

    # --------------------------------------------------------
    # FIRST RESULT
    # --------------------------------------------------------

    async def first(
        self,
        query: str,
    ) -> Optional[SearchResult]:

        results = await self.search(
            query,
            1,
        )

        return results[0] if results else None

    # --------------------------------------------------------
    # RESOLVE URL / QUERY
    # --------------------------------------------------------

    async def resolve(
        self,
        url_or_query: str,
    ) -> Optional[SearchResult]:

        value = _clean_query(url_or_query)

        if not value:
            return None

        # ----------------------------------------------------
        # Direct YouTube URL
        # ----------------------------------------------------

        if self._url_re.search(value):

            VideosSearch = self._get_search_class()

            if VideosSearch is not None:

                try:
                    search = VideosSearch(
                        value,
                        limit=1,
                    )

                    payload = await search.next()

                    rows = (
                        payload.get("result", [])
                        if isinstance(payload, dict)
                        else []
                    )

                    if rows:

                        row = rows[0]

                        if isinstance(row, dict):

                            result = self._parse_row(row)

                            if result:
                                return result

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logger.exception(
                        "YouTube URL resolve failed"
                    )

            # Fallback for direct URL.
            return SearchResult(
                title=value,
                url=_clean_url(value) or value,
                source="youtube",
            )

        # ----------------------------------------------------
        # Normal search query
        # ----------------------------------------------------

        return await self.first(value)


# ============================================================
# SINGLETON
# ============================================================

_searcher: Optional[YouTubeSearcher] = None


def get_searcher() -> YouTubeSearcher:

    global _searcher

    if _searcher is None:
        _searcher = YouTubeSearcher()

    return _searcher


def reset_searcher() -> None:

    global _searcher

    _searcher = None

    _search_cache.clear()
    _pending_searches.clear()


# ============================================================
# PUBLIC HELPERS
# ============================================================

async def search_tracks(
    query: str,
    limit: int = 5,
) -> list[SearchResult]:

    return await get_searcher().search(
        query,
        limit,
    )


async def search_track(
    query: str,
) -> Optional[SearchResult]:

    return await get_searcher().first(
        query
    )


__all__ = [
    "SearchResult",
    "YouTubeSearcher",
    "get_searcher",
    "reset_searcher",
    "search_tracks",
    "search_track",
]
