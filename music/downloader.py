import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from config import (
    MUSIC_DOWNLOAD_DIR,
    MUSIC_MAX_FILE_SIZE_MB,
)

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(MUSIC_DOWNLOAD_DIR)
DOWNLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

MAX_BYTES = (
    int(MUSIC_MAX_FILE_SIZE_MB)
    * 1024
    * 1024
)


class MusicDownloader:

    def __init__(
        self,
        download_dir: str | Path | None = None,
    ) -> None:

        self.download_dir = Path(
            download_dir or DOWNLOAD_DIR
        )

        self.download_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ========================================================
    # COOKIES
    # ========================================================

    def _cookies(self) -> Optional[str]:

        configured = os.getenv(
            "YOUTUBE_COOKIES_FILE",
            "",
        ).strip()

        if configured:

            path = Path(configured)

            if path.is_file():
                logger.info(
                    "YouTube cookies enabled: %s",
                    path,
                )
                return str(path)

            logger.warning(
                "YOUTUBE_COOKIES_FILE configured but file "
                "does not exist: %s",
                path,
            )

        root = Path.cwd() / "cookies"

        if root.exists():

            files = sorted(
                root.glob("*.txt")
            )

            if files:

                logger.info(
                    "Using YouTube cookies file: %s",
                    files[0],
                )

                return str(files[0])

        logger.info(
            "No YouTube cookies configured."
        )

        return None

    # ========================================================
    # HEADERS
    # ========================================================

    @staticmethod
    def _headers() -> dict:

        return {
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 "
                "Safari/537.36"
            ),
            "Accept-Language": (
                "en-US,en;q=0.9"
            ),
        }

    # ========================================================
    # OPTIONS
    # ========================================================

    def _opts(
        self,
        video: bool,
        player_client: str = "web",
    ) -> dict:

        if video:

            media_format = (
                "best[height<=360][ext=mp4]"
                "/best[height<=360]"
                "/best"
            )

        else:

            media_format = (
                "bestaudio[ext=m4a]"
                "/bestaudio"
                "/best"
            )

        opts = {
            "quiet": True,
            "no_warnings": False,

            "noplaylist": True,

            "geo_bypass": True,
            "nocheckcertificate": True,

            "retries": 2,
            "fragment_retries": 2,

            "socket_timeout": 20,

            "continuedl": False,
            "overwrites": False,

            "http_headers": self._headers(),

            "outtmpl": str(
                self.download_dir
                / "%(id)s.%(ext)s"
            ),

            "format": media_format,

            "extractor_args": {
                "youtube": {
                    "player_client": [
                        player_client
                    ],
                }
            },
        }

        cookie = self._cookies()

        if cookie:
            opts["cookiefile"] = cookie

        return opts

    # ========================================================
    # FIND MEDIA
    # ========================================================

    def _find_media(
        self,
        video_id: str,
    ) -> Optional[Path]:

        candidates = []

        for path in self.download_dir.glob(
            f"{video_id}.*"
        ):

            if not path.is_file():
                continue

            if path.name.endswith(".part"):
                continue

            if path.name.endswith(".ytdl"):
                continue

            try:

                size = path.stat().st_size

            except OSError:

                continue

            if size <= 0:
                continue

            candidates.append(path)

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda p: p.stat().st_mtime,
        )

    # ========================================================
    # PARTIAL CLEANUP
    # ========================================================

    def _remove_partial(
        self,
        video_id: str,
    ) -> None:

        patterns = (
            f"{video_id}.*.part",
            f"{video_id}.*.ytdl",
        )

        for pattern in patterns:

            for path in self.download_dir.glob(
                pattern
            ):

                try:

                    path.unlink(
                        missing_ok=True
                    )

                except Exception:

                    logger.debug(
                        "Could not remove partial file: %s",
                        path,
                        exc_info=True,
                    )

    # ========================================================
    # DOWNLOAD PROFILE
    # ========================================================

    def _download_with_profile(
        self,
        url: str,
        video: bool,
        opts: dict,
    ) -> tuple[str, dict]:

        import yt_dlp

        with yt_dlp.YoutubeDL(opts) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

            if not info:

                raise ValueError(
                    "No YouTube metadata."
                )

            video_id = str(
                info.get("id") or ""
            )

            if not video_id:

                raise ValueError(
                    "YouTube video ID missing."
                )

            existing = self._find_media(
                video_id
            )

            if existing:

                path = existing

                logger.info(
                    "Using existing media: %s",
                    path,
                )

            else:

                self._remove_partial(
                    video_id
                )

                ydl.download(
                    [url]
                )

                path = self._find_media(
                    video_id
                )

                if path is None:

                    raise FileNotFoundError(
                        "yt-dlp produced no media."
                    )

            if not path.exists():

                raise FileNotFoundError(
                    str(path)
                )

            size = path.stat().st_size

            if size <= 0:

                raise ValueError(
                    "Downloaded file is empty."
                )

            if size > MAX_BYTES:

                try:

                    path.unlink(
                        missing_ok=True
                    )

                except Exception:

                    pass

                raise ValueError(
                    "Downloaded media exceeds "
                    "MUSIC_MAX_FILE_SIZE_MB."
                )

            return (
                str(path),
                info,
            )

    # ========================================================
    # ERROR CLASSIFICATION
    # ========================================================

    @staticmethod
    def _is_youtube_auth_error(
        error: Exception,
    ) -> bool:

        text = str(error).lower()

        keywords = (
            "sign in to confirm",
            "not a bot",
            "confirm you're not a bot",
            "confirm you’re not a bot",
            "cookies",
            "po token",
            "potoken",
            "authentication required",
        )

        return any(
            keyword in text
            for keyword in keywords
        )

    # ========================================================
    # SYNC DOWNLOAD
    # ========================================================

    def _download_sync(
        self,
        url: str,
        video: bool,
    ) -> tuple[str, dict]:

        last_error: Optional[Exception] = None

        # Keep this conservative.
        #
        # These are normal yt-dlp supported client
        # configurations. We do not attempt to bypass
        # YouTube anti-bot protections.
        clients = (
            "web",
            "android",
            "mweb",
        )

        for client in clients:

            opts = self._opts(
                video=video,
                player_client=client,
            )

            try:

                logger.info(
                    "YouTube download client=%s video=%s",
                    client,
                    video,
                )

                result = (
                    self._download_with_profile(
                        url=url,
                        video=video,
                        opts=opts,
                    )
                )

                logger.info(
                    "YouTube download successful "
                    "client=%s video=%s",
                    client,
                    video,
                )

                return result

            except Exception as exc:

                last_error = exc

                if self._is_youtube_auth_error(
                    exc
                ):

                    logger.warning(
                        "YouTube requires authentication "
                        "or additional verification. "
                        "client=%s",
                        client,
                    )

                else:

                    logger.warning(
                        "Download failed client=%s: %s",
                        client,
                        exc,
                    )

                self._remove_partial_from_url(
                    url
                )

        if last_error:

            raise last_error

        raise RuntimeError(
            "All YouTube download profiles failed."
        )

    # ========================================================
    # CLEAN PARTIAL FROM URL
    # ========================================================

    def _remove_partial_from_url(
        self,
        url: str,
    ) -> None:

        try:

            import yt_dlp

            with yt_dlp.YoutubeDL(
                {
                    "quiet": True,
                    "no_warnings": True,
                }
            ) as ydl:

                video_id = (
                    ydl.extract_info(
                        url,
                        download=False,
                    ).get("id")
                )

            if video_id:

                self._remove_partial(
                    str(video_id)
                )

        except Exception:

            logger.debug(
                "Could not cleanup partial YouTube "
                "download for %s",
                url,
                exc_info=True,
            )

    # ========================================================
    # YOUTUBE DOWNLOAD
    # ========================================================

    async def download_youtube(
        self,
        url: str,
        *,
        video: bool = False,
    ) -> Optional[tuple[str, dict]]:

        if not url:
            return None

        try:

            return await asyncio.to_thread(
                self._download_sync,
                url,
                video,
            )

        except Exception as exc:

            if self._is_youtube_auth_error(
                exc
            ):

                logger.error(
                    "YouTube requires authentication "
                    "or verification: %s",
                    url,
                )

            else:

                logger.exception(
                    "YouTube download failed: %s",
                    url,
                )

            return None

    # ========================================================
    # GENERIC DOWNLOAD
    # ========================================================

    async def download(
        self,
        track,
        *,
        video: bool = False,
    ) -> Optional[str]:

        if track is None:
            return None

        # ----------------------------------------------------
        # DICT
        # ----------------------------------------------------

        if isinstance(
            track,
            dict,
        ):

            path = (
                track.get("audio_path")
                or track.get("path")
            )

            url = (
                track.get("url")
                or track.get("link")
            )

        # ----------------------------------------------------
        # OBJECT
        # ----------------------------------------------------

        else:

            path = getattr(
                track,
                "audio_path",
                None,
            )

            url = getattr(
                track,
                "url",
                None,
            )

        # ----------------------------------------------------
        # LOCAL FILE
        # ----------------------------------------------------

        if path:

            local = Path(path)

            if local.is_file():

                try:

                    if local.stat().st_size <= MAX_BYTES:

                        return str(local)

                except OSError:

                    pass

        # ----------------------------------------------------
        # URL
        # ----------------------------------------------------

        if not url:
            return None

        result = await self.download_youtube(
            url,
            video=video,
        )

        if not result:
            return None

        return result[0]

    # ========================================================
    # DELETE
    # ========================================================

    async def delete(
        self,
        path: str | Path,
    ) -> bool:

        try:

            p = Path(path).resolve()

            root = (
                self.download_dir.resolve()
            )

            # Security:
            # only delete files inside download dir.
            p.relative_to(root)

            if p.exists():

                p.unlink(
                    missing_ok=True
                )

            return True

        except Exception:

            logger.warning(
                "Failed deleting media: %s",
                path,
                exc_info=True,
            )

            return False

    # ========================================================
    # CLEANUP
    # ========================================================

    async def cleanup(self) -> int:

        count = 0

        try:

            files = list(
                self.download_dir.iterdir()
            )

        except Exception:

            return 0

        for path in files:

            if not path.is_file():
                continue

            try:

                path.unlink()
                count += 1

            except OSError:

                pass

        logger.info(
            "Music downloader cleanup: %s files removed.",
            count,
        )

        return count


# ============================================================
# GLOBAL DOWNLOADER
# ============================================================

_downloader: Optional[
    MusicDownloader
] = None


def get_downloader() -> MusicDownloader:

    global _downloader

    if _downloader is None:

        _downloader = MusicDownloader()

    return _downloader


def reset_downloader() -> None:

    global _downloader

    _downloader = None


# ============================================================
# HELPER
# ============================================================

async def download_track(
    track,
    video: bool = False,
) -> Optional[str]:

    return await get_downloader().download(
        track,
        video=video,
    )


__all__ = [
    "MusicDownloader",
    "get_downloader",
    "reset_downloader",
    "download_track",
]
