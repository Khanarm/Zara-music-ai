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

DOWNLOAD_DIR = Path(MUSIC_DOWNLOAD_DIR)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_BYTES = int(MUSIC_MAX_FILE_SIZE_MB) * 1024 * 1024


class MusicDownloader:
    """
    Zara Music YouTube downloader.

    Flow:

        YouTube URL
            ↓
        yt-dlp
            ↓
        local media file
            ↓
        FFmpeg
            ↓
        normalized MP3
            ↓
        PyTgCalls playback

    The downloader keeps the public API used by the rest
    of the Zara Music system unchanged.
    """

    # ========================================================
    # INIT
    # ========================================================

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

            path = Path(
                configured
            )

            if path.is_file():

                logger.info(
                    "Using YouTube cookies: %s",
                    path,
                )

                return str(path)

            logger.warning(
                "YOUTUBE_COOKIES_FILE configured "
                "but file does not exist: %s",
                path,
            )

        # ----------------------------------------------------
        # Local cookies directory
        # ----------------------------------------------------

        root = (
            Path.cwd()
            / "cookies"
        )

        if root.exists():

            files = sorted(
                root.glob("*.txt")
            )

            if files:

                logger.info(
                    "Using local YouTube cookies: %s",
                    files[0],
                )

                return str(
                    files[0]
                )

        return None

    # ========================================================
    # FFMPEG
    # ========================================================

    @staticmethod
    def _ffmpeg_available() -> bool:

        try:

            result = subprocess.run(
                [
                    "ffmpeg",
                    "-version",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )

            return (
                result.returncode == 0
            )

        except Exception:

            return False

    # ========================================================
    # COMMON HEADERS
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
    # YT-DLP OPTIONS
    # ========================================================

    def _opts(
        self,
        video: bool,
        player_client: str = "web",
    ) -> dict:

        opts = {
            # ------------------------------------------------
            # General
            # ------------------------------------------------

            "geo_bypass": True,
            "nocheckcertificate": True,

            "quiet": True,
            "no_warnings": True,

            "noplaylist": True,

            "retries": 5,
            "fragment_retries": 5,

            "continuedl": False,

            "overwrites": False,

            "socket_timeout": 30,

            # ------------------------------------------------
            # HTTP
            # ------------------------------------------------

            "http_headers": self._headers(),

            # ------------------------------------------------
            # Output
            # ------------------------------------------------

            "outtmpl": str(
                self.download_dir
                / "%(id)s.%(ext)s"
            ),

            # ------------------------------------------------
            # YouTube extractor
            # ------------------------------------------------

            "extractor_args": {
                "youtube": {
                    "player_client": [
                        player_client
                    ],
                }
            },
        }

        # ----------------------------------------------------
        # Cookies
        # ----------------------------------------------------

        cookie = self._cookies()

        if cookie:

            opts[
                "cookiefile"
            ] = cookie

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        if video:

            opts.update(
                {
                    "format": (
                        "bestvideo[height<=720]"
                        "[width<=1280]"
                        "[ext=mp4]"
                        "+bestaudio[ext=m4a]"
                        "/best[height<=720]"
                        "[width<=1280]"
                        "/best"
                    ),

                    "merge_output_format": "mp4",

                    "prefer_ffmpeg": True,
                }
            )

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        else:

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
    # DOWNLOAD CONFIGURATIONS
    # ========================================================

    def _download_profiles(
        self,
        video: bool,
    ) -> list[dict]:

        """
        Different YouTube clients are attempted in order.

        This is intentionally kept small so a failed request
        does not create excessive traffic.
        """

        profiles = []

        # ----------------------------------------------------
        # First attempt: web
        # ----------------------------------------------------

        profiles.append(
            self._opts(
                video=video,
                player_client="web",
            )
        )

        # ----------------------------------------------------
        # Second attempt: android
        # ----------------------------------------------------

        profiles.append(
            self._opts(
                video=video,
                player_client="android",
            )
        )

        # ----------------------------------------------------
        # Third attempt: mweb
        # ----------------------------------------------------

        profiles.append(
            self._opts(
                video=video,
                player_client="mweb",
            )
        )

        return profiles

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

            try:

                size = path.stat().st_size

                if size <= 0:
                    continue

            except OSError:

                continue

            # ------------------------------------------------
            # Ignore normalized MP3
            # ------------------------------------------------

            if path.stem.endswith(
                "_zara"
            ):
                continue

            candidates.append(
                path
            )

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda p: p.stat().st_mtime,
        )

    # ========================================================
    # REMOVE PARTIAL FILES
    # ========================================================

    def _remove_partial(
        self,
        video_id: str,
    ) -> None:

        patterns = [
            f"{video_id}.*.part",
            f"{video_id}.*.ytdl",
        ]

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
                        "Could not remove partial "
                        "file: %s",
                        path,
                        exc_info=True,
                    )

    # ========================================================
    # CONVERT AUDIO
    # ========================================================

    async def _convert_audio(
        self,
        source: Path,
        video_id: str,
    ) -> Optional[Path]:

        if not source.exists():
            return None

        if not self._ffmpeg_available():

            logger.error(
                "FFmpeg binary is not available."
            )

            return None

        output = (
            self.download_dir
            / f"{video_id}_zara.mp3"
        )

        # ----------------------------------------------------
        # Already converted
        # ----------------------------------------------------

        if output.exists():

            try:

                if output.stat().st_size > 0:
                    return output

            except OSError:

                pass

        command = [
            "ffmpeg",
            "-y",

            "-hide_banner",
            "-loglevel",
            "error",

            "-i",
            str(source),

            "-vn",

            "-ac",
            "2",

            "-ar",
            "48000",

            "-c:a",
            "libmp3lame",

            "-b:a",
            "128k",

            str(output),
        ]

        logger.info(
            "Converting audio with FFmpeg: %s",
            source.name,
        )

        try:

            process = (
                await asyncio.create_subprocess_exec(
                    *command,
                    stdout=(
                        asyncio.subprocess.PIPE
                    ),
                    stderr=(
                        asyncio.subprocess.PIPE
                    ),
                )
            )

            stdout, stderr = (
                await process.communicate()
            )

            if process.returncode != 0:

                error = (
                    stderr.decode(
                        errors="ignore"
                    ).strip()
                )

                logger.error(
                    "FFmpeg conversion failed: %s",
                    error[-2000:],
                )

                output.unlink(
                    missing_ok=True
                )

                return None

            if not output.exists():

                logger.error(
                    "FFmpeg completed but output "
                    "file was not created."
                )

                return None

            if output.stat().st_size <= 0:

                logger.error(
                    "FFmpeg created an empty file."
                )

                output.unlink(
                    missing_ok=True
                )

                return None

            logger.info(
                "Audio normalized successfully: %s",
                output,
            )

            return output

        except Exception:

            logger.exception(
                "Audio FFmpeg conversion failed."
            )

            output.unlink(
                missing_ok=True
            )

            return None

    # ========================================================
    # DOWNLOAD ONE PROFILE
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

            # ------------------------------------------------
            # Get metadata first
            # ------------------------------------------------

            info = ydl.extract_info(
                url,
                download=False,
            )

            if not info:

                raise ValueError(
                    "yt-dlp returned no metadata"
                )

            video_id = str(
                info.get("id")
                or ""
            )

            if not video_id:

                raise ValueError(
                    "YouTube video ID missing"
                )

            # ------------------------------------------------
            # Existing file
            # ------------------------------------------------

            existing = (
                self._find_media(
                    video_id
                )
            )

            if existing:

                logger.info(
                    "Using existing media: %s",
                    existing,
                )

                path = existing

            else:

                self._remove_partial(
                    video_id
                )

                logger.info(
                    "Starting yt-dlp download "
                    "for video=%s",
                    video_id,
                )

                ydl.download(
                    [url]
                )

                path = (
                    self._find_media(
                        video_id
                    )
                )

                if path is None:

                    raise FileNotFoundError(
                        "yt-dlp completed without "
                        "producing a media file"
                    )

            # ------------------------------------------------
            # Validate
            # ------------------------------------------------

            if not path.exists():

                raise FileNotFoundError(
                    str(path)
                )

            size = path.stat().st_size

            if size <= 0:

                raise ValueError(
                    "Downloaded media is empty."
                )

            if size > MAX_BYTES:

                path.unlink(
                    missing_ok=True
                )

                raise ValueError(
                    "Downloaded media exceeds "
                    "MUSIC_MAX_FILE_SIZE_MB"
                )

            return (
                str(path),
                info,
            )

    # ========================================================
    # DOWNLOAD SYNC
    # ========================================================

    def _download_sync(
        self,
        url: str,
        video: bool,
    ) -> tuple[str, dict]:

        last_error = None

        profiles = (
            self._download_profiles(
                video
            )
        )

        for index, opts in enumerate(
            profiles,
            1,
        ):

            client = (
                opts
                .get(
                    "extractor_args",
                    {}
                )
                .get(
                    "youtube",
                    {}
                )
                .get(
                    "player_client",
                    ["unknown"],
                )[0]
            )

            logger.info(
                "YouTube download attempt %s/%s "
                "using client=%s",
                index,
                len(profiles),
                client,
            )

            try:

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
                    "YouTube download attempt failed "
                    "using client=%s: %s",
                    client,
                    exc,
                )

                # Remove incomplete files before
                # trying another profile.
                try:

                    import yt_dlp

                    # Extract ID without downloading
                    basic_opts = {
                        "quiet": True,
                        "no_warnings": True,
                        "noplaylist": True,
                    }

                    with yt_dlp.YoutubeDL(
                        basic_opts
                    ) as ydl:

                        info = (
                            ydl.extract_info(
                                url,
                                download=False,
                            )
                        )

                    if info:

                        video_id = str(
                            info.get("id")
                            or ""
                        )

                        if video_id:

                            self._remove_partial(
                                video_id
                            )

                except Exception:

                    logger.debug(
                        "Partial-file cleanup failed.",
                        exc_info=True,
                    )

        if last_error:

            raise last_error

        raise RuntimeError(
            "All YouTube download profiles failed."
        )

    # ========================================================
    # DOWNLOAD YOUTUBE
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

            path, info = await asyncio.to_thread(
                self._download_sync,
                url,
                video,
            )

            source = Path(
                path
            )

            # ------------------------------------------------
            # Normalize audio
            # ------------------------------------------------

            if not video:

                normalized = (
                    await self._convert_audio(
                        source,
                        str(
                            info.get("id")
                        ),
                    )
                )

                if normalized is None:
                    return None

                # ------------------------------------------------
                # Remove original source
                # ------------------------------------------------

                if (
                    normalized.resolve()
                    != source.resolve()
                ):

                    try:

                        source.unlink(
                            missing_ok=True
                        )

                    except Exception:

                        logger.warning(
                            "Could not remove original "
                            "audio file: %s",
                            source,
                        )

                path = str(
                    normalized
                )

            return (
                path,
                info,
            )

        except Exception:

            logger.exception(
                "yt-dlp download failed: %s",
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
        # Dict track
        # ----------------------------------------------------

        if isinstance(
            track,
            dict,
        ):

            path = (
                track.get(
                    "audio_path"
                )
                or track.get(
                    "path"
                )
            )

            url = (
                track.get(
                    "url"
                )
                or track.get(
                    "link"
                )
            )

        # ----------------------------------------------------
        # Track object
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
        # Existing local file
        # ----------------------------------------------------

        if path:

            local = Path(
                path
            )

            if local.is_file():

                if video:
                    return str(local)

                if local.name.endswith(
                    "_zara.mp3"
                ):

                    return str(local)

        # ----------------------------------------------------
        # No URL
        # ----------------------------------------------------

        if not url:
            return None

        # ----------------------------------------------------
        # Download
        # ----------------------------------------------------

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

            p = Path(
                path
            ).resolve()

            root = (
                self.download_dir
                .resolve()
            )

            # Security: only delete files
            # inside download directory.
            p.relative_to(
                root
            )

            p.unlink(
                missing_ok=True
            )

            return True

        except Exception:

            logger.exception(
                "Failed deleting media: %s",
                path,
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

            logger.exception(
                "Failed reading music directory."
            )

            return 0

        for path in files:

            if not path.is_file():
                continue

            try:

                path.unlink()

                count += 1

            except OSError:

                logger.exception(
                    "Failed deleting %s",
                    path,
                )

        return count


# ============================================================
# SINGLETON
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
