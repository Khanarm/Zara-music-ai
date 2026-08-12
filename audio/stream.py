# audio/stream.py

import asyncio
import logging
import os
from typing import Optional

from pytgcalls import PyTgCalls
from pytgcalls.types import AudioQuality, MediaStream, RecordStream, VideoQuality
from pytgcalls.exceptions import GroupCallNotFoundError

logger = logging.getLogger(__name__)


class AudioStream:
    """Telegram VC media engine for Zara."""

    def __init__(self, client, calls: PyTgCalls):
        self.client = client
        self.calls = calls
        self.current_streams: dict[int, str] = {}
        self.current_media: dict[int, str] = {}
        self.recording_chats: set[int] = set()

    async def start(self) -> None:
        await self.calls.start()
        logger.info("PyTgCalls started")

    async def join_and_record(self, chat_id: int) -> bool:
        """Join an active VC and enable incoming microphone frames."""
        try:
            await self.calls.record(
                chat_id,
                RecordStream(True, AudioQuality.HIGH),
            )
            self.recording_chats.add(int(chat_id))
            return True
        except GroupCallNotFoundError:
            logger.warning("No active voice chat in %s", chat_id)
            return False
        except Exception:
            logger.exception("Failed joining/recording VC %s", chat_id)
            return False

    async def stop_recording(self, chat_id: int) -> None:
        self.recording_chats.discard(int(chat_id))

    async def play(self, chat_id: int, media_path: str, *, video: bool = False) -> bool:
        if not media_path or not os.path.isfile(media_path):
            logger.error("Media file does not exist: %s", media_path)
            return False
        try:
            if video:
                stream = MediaStream(
                    media_path,
                    AudioQuality.HIGH,
                    VideoQuality.HD_720p,
                )
            else:
                stream = MediaStream(
                    media_path,
                    audio_parameters=AudioQuality.HIGH,
                    video_flags=MediaStream.Flags.IGNORE,
                )

            await self.calls.play(int(chat_id), stream)
            self.current_streams[int(chat_id)] = media_path
            self.current_media[int(chat_id)] = "video" if video else "audio"
            return True
        except GroupCallNotFoundError:
            logger.warning("No active voice chat in %s", chat_id)
            return False
        except Exception:
            logger.exception("Failed playing media in %s", chat_id)
            return False

    async def stop(self, chat_id: int) -> bool:
        chat_id = int(chat_id)
        try:
            if chat_id in self.recording_chats:
                # Keep Zara inside the VC and keep receiving user audio.
                await self.calls.record(chat_id, RecordStream(True, AudioQuality.HIGH))
            else:
                await self.calls.leave_call(chat_id)
            self.current_streams.pop(chat_id, None)
            self.current_media.pop(chat_id, None)
            return True
        except GroupCallNotFoundError:
            self.current_streams.pop(chat_id, None)
            self.current_media.pop(chat_id, None)
            return False
        except Exception:
            logger.exception("Failed stopping stream in %s", chat_id)
            return False

    async def pause(self, chat_id: int) -> bool:
        try:
            await self.calls.pause(int(chat_id))
            return True
        except Exception:
            logger.exception("Failed pausing stream in %s", chat_id)
            return False

    async def resume(self, chat_id: int) -> bool:
        try:
            await self.calls.resume(int(chat_id))
            return True
        except Exception:
            logger.exception("Failed resuming stream in %s", chat_id)
            return False

    async def leave(self, chat_id: int) -> bool:
        return await self.stop(chat_id)

    def is_playing(self, chat_id: int) -> bool:
        return int(chat_id) in self.current_streams

    def get_current_stream(self, chat_id: int) -> Optional[str]:
        return self.current_streams.get(int(chat_id))

    def get_current_media_type(self, chat_id: int) -> Optional[str]:
        return self.current_media.get(int(chat_id))

    async def change_stream(self, chat_id: int, media_path: str, *, video: bool = False) -> bool:
        if self.is_playing(chat_id):
            await self.stop(chat_id)
            await asyncio.sleep(0.25)
        return await self.play(chat_id, media_path, video=video)

    async def cleanup(self) -> None:
        for chat_id in list(self.current_streams):
            await self.stop(chat_id)
        self.recording_chats.clear()
