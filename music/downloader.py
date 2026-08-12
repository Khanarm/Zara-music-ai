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
    YouTube downloader for Zara Music.

    Downloads using yt-dlp and converts audio to a predictable
    MP3 format using the system FFmpeg binary.

    FFmpeg is installed by the project's Dockerfile.
    """

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
    # FFMPEG CHECK
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

            return result.returncode == 0

        except Exception:
            return False

    # ========================================================
    # YT-DLP OPTIONS
    # ========================================================

    def _opts(
        self,
        video: bool,
    ) -> dict:

        opts = {
            "geo_bypass": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,

            # Keep original extension until FFmpeg
            # conversion is completed.
            "outtmpl": str(
                self.download_dir
                / "%(id)s.%(ext)s"
            ),
        }

        cookie = self._cookies()

        if cookie:
            opts["cookiefile"] = cookie

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        if video:

            opts.update(
                {
                    "format": (
                        "bestvideo[height<=720]"
                        "[width<=1280][ext=mp4]"
                        "+bestaudio[ext=m4a]"
                        "/best[height<=720]"
                        "[width<=1280]"
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
    # FIND DOWNLOADED FILE
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
                if path.stat().st_size <= 0:
                    continue
            except OSError:
                continue

            # Ignore our generated normalized files.
            if path.stem.endswith("_zara"):
                continue

            candidates.append(path)

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda p: p.stat().st_mtime,
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

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

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
    # DOWNLOAD SYNC
    # ========================================================

    def _download_sync(
        self,
        url: str,
        video: bool,
    ) -> tuple[str, dict]:

        import yt_dlp

        opts = self._opts(video)

        logger.info(
            "Downloading media: %s",
            url,
        )

        with yt_dlp.YoutubeDL(
            opts
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False,
            )

            video_id = str(
                info.get("id")
            )

            existing = self._find_media(
                video_id
            )

            if existing:

                path = existing

            else:

                ydl.download(
                    [url]
                )

                path = self._find_media(
                    video_id
                )

                if path is None:

                    raise FileNotFoundError(
                        "yt-dlp completed without "
                        "producing a media file"
                    )

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

            source = Path(path)

            # ------------------------------------------------
            # Audio normalization
            # ------------------------------------------------

            if not video:

                normalized = await self._convert_audio(
                    source,
                    str(info.get("id")),
                )

                if normalized is None:
                    return None

                # Delete original downloaded file after
                # successful normalization.
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

                path = str(normalized)

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

        if isinstance(track, dict):

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

        # Existing local file.
        if path:

            local = Path(path)

            if local.is_file():

                if video:
                    return str(local)

                # Already normalized.
                if local.name.endswith(
                    "_zara.mp3"
                ):
                    return str(local)

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
            root = self.download_dir.resolve()

            p.relative_to(root)

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

        for path in self.download_dir.iterdir():

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
