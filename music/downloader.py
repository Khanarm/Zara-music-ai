import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from config import (
    MUSIC_DOWNLOAD_DIR,
    MUSIC_MAX_FILE_SIZE_MB,
)

logger = logging.getLogger(__name__)

DOWNLOAD_DIR = Path(
    MUSIC_DOWNLOAD_DIR
)

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
    ):

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
                return str(path)

        root = Path.cwd() / "cookies"

        if root.exists():

            files = sorted(
                root.glob("*.txt")
            )

            if files:
                return str(files[0])

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

        opts = {
            "quiet": True,
            "no_warnings": True,

            "noplaylist": True,

            "geo_bypass": True,
            "nocheckcertificate": True,

            "retries": 3,
            "fragment_retries": 3,

            "socket_timeout": 20,

            "continuedl": False,
            "overwrites": False,

            "http_headers": self._headers(),

            "outtmpl": str(
                self.download_dir
                / "%(id)s.%(ext)s"
            ),

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

        if video:

            # 360p max.
            #
            # Prefer a single MP4 when available
            # to avoid unnecessary merge work.
            opts.update(
                {
                    "format": (
                        "best[height<=360]"
                        "[ext=mp4]"
                        "/best[height<=360]"
                        "/best"
                    ),
                }
            )

        else:

            # Audio only.
            #
            # No MP3 conversion here.
            opts.update(
                {
                    "format": (
                        "bestaudio[ext=m4a]"
                        "/bestaudio"
                        "/best"
                    ),
                }
            )

        return opts

    # ========================================================
    # FIND FILE
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

            if path.name.endswith(
                ".part"
            ):
                continue

            if path.name.endswith(
                ".ytdl"
            ):
                continue

            try:

                if path.stat().st_size <= 0:
                    continue

            except OSError:
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
                    pass

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

        with yt_dlp.YoutubeDL(
            opts
        ) as ydl:

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

                path.unlink(
                    missing_ok=True
                )

                raise ValueError(
                    "Downloaded media exceeds "
                    "MUSIC_MAX_FILE_SIZE_MB."
                )

            return (
                str(path),
                info,
            )

    # ========================================================
    # SYNC DOWNLOAD
    # ========================================================

    def _download_sync(
        self,
        url: str,
        video: bool,
    ) -> tuple[str, dict]:

        last_error = None

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
                    "YouTube download "
                    "client=%s video=%s",
                    client,
                    video,
                )

                return (
                    self._download_with_profile(
                        url,
                        video,
                        opts,
                    )
                )

            except Exception as exc:

                last_error = exc

                logger.warning(
                    "Download failed client=%s: %s",
                    client,
                    exc,
                )

        if last_error:
            raise last_error

        raise RuntimeError(
            "All download profiles failed."
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

        except Exception:

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

        if path:

            local = Path(path)

            if local.is_file():
                return str(local)

        if not url:
            return None

        result = (
            await self.download_youtube(
                url,
                video=video,
            )
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
                self.download_dir
                .resolve()
            )

            p.relative_to(root)

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

        return count


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
