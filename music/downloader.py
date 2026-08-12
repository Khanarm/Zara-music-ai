# music/downloader.py

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from config import MUSIC_DOWNLOAD_DIR, MUSIC_MAX_FILE_SIZE_MB

logger = logging.getLogger(__name__)
DOWNLOAD_DIR = Path(MUSIC_DOWNLOAD_DIR)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_BYTES = int(MUSIC_MAX_FILE_SIZE_MB) * 1024 * 1024


class MusicDownloader:
    """YouTube downloader using the same yt-dlp strategy as the reference project."""

    def __init__(self, download_dir: str | Path | None = None):
        self.download_dir = Path(download_dir or DOWNLOAD_DIR)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _cookies(self) -> Optional[str]:
        configured = os.getenv("YOUTUBE_COOKIES_FILE", "").strip()
        if configured and Path(configured).is_file():
            return configured
        root = Path.cwd() / "cookies"
        files = sorted(root.glob("*.txt")) if root.exists() else []
        return str(files[0]) if files else None

    def _opts(self, video: bool) -> dict:
        opts = {
            "geo_bypass": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "outtmpl": str(self.download_dir / "%(id)s.%(ext)s"),
        }
        cookie = self._cookies()
        if cookie:
            opts["cookiefile"] = cookie
        if video:
            opts.update({
                "format": "bestvideo[height<=720][width<=1280][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][width<=1280]",
                "merge_output_format": "mp4",
                "prefer_ffmpeg": True,
            })
        else:
            opts["format"] = "bestaudio/best"
        return opts

    def _download_sync(self, url: str, video: bool) -> tuple[str, dict]:
        import yt_dlp
        opts = self._opts(video)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_id = str(info.get("id"))
            existing = list(self.download_dir.glob(f"{video_id}.*"))
            existing = [p for p in existing if p.is_file() and p.stat().st_size > 0]
            if existing:
                path = existing[0]
            else:
                ydl.download([url])
                candidates = list(self.download_dir.glob(f"{video_id}.*"))
                if not candidates:
                    raise FileNotFoundError("yt-dlp completed without producing a file")
                path = max(candidates, key=lambda p: p.stat().st_mtime)
            if path.stat().st_size > MAX_BYTES:
                path.unlink(missing_ok=True)
                raise ValueError("Downloaded media exceeds MUSIC_MAX_FILE_SIZE_MB")
            return str(path), info

    async def download_youtube(self, url: str, *, video: bool = False) -> Optional[tuple[str, dict]]:
        if not url:
            return None
        try:
            return await asyncio.to_thread(self._download_sync, url, video)
        except Exception:
            logger.exception("yt-dlp download failed: %s", url)
            return None

    async def download(self, track, *, video: bool = False) -> Optional[str]:
        if track is None:
            return None
        if isinstance(track, dict):
            path = track.get("audio_path") or track.get("path")
            url = track.get("url") or track.get("link")
        else:
            path = getattr(track, "audio_path", None)
            url = getattr(track, "url", None)
        if path and Path(path).is_file():
            return str(path)
        if url:
            result = await self.download_youtube(url, video=video)
            if result:
                return result[0]
        return None

    async def delete(self, path: str | Path) -> bool:
        try:
            p = Path(path).resolve()
            root = self.download_dir.resolve()
            p.relative_to(root)
            p.unlink(missing_ok=True)
            return True
        except Exception:
            logger.exception("Failed deleting media: %s", path)
            return False

    async def cleanup(self) -> int:
        count = 0
        for p in self.download_dir.iterdir():
            if p.is_file():
                try:
                    p.unlink()
                    count += 1
                except OSError:
                    logger.exception("Failed deleting %s", p)
        return count


_downloader: Optional[MusicDownloader] = None


def get_downloader() -> MusicDownloader:
    global _downloader
    if _downloader is None:
        _downloader = MusicDownloader()
    return _downloader


def reset_downloader() -> None:
    global _downloader
    _downloader = None


async def download_track(track, video: bool = False) -> Optional[str]:
    return await get_downloader().download(track, video=video)


__all__ = ["MusicDownloader", "get_downloader", "reset_downloader", "download_track"]
