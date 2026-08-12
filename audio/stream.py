import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

logger = logging.getLogger(__name__)


class AudioStream:
    """Zara music playback engine for PyTgCalls 2.x."""

    def __init__(
        self,
        client,
        calls: PyTgCalls,
    ):
        self.client = client
        self.calls = calls

        self.current_streams: dict[int, str] = {}
        self.current_media: dict[int, str] = {}
        self.connected_chats: set[int] = set()

        self._locks: dict[int, asyncio.Lock] = {}

    def _lock(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(
            int(chat_id),
            asyncio.Lock(),
        )

    async def start(self) -> None:
        try:
            result = self.calls.start()

            if hasattr(result, "__await__"):
                await result

            logger.info("PyTgCalls started successfully.")

        except Exception:
            logger.exception("Failed to start PyTgCalls.")
            raise

    async def play(
        self,
        chat_id: int,
        media_path: str,
        *,
        video: bool = False,
    ) -> bool:

        chat_id = int(chat_id)

        if not media_path:
            logger.error("PLAY FAILED: empty media path.")
            return False

        path = Path(media_path).resolve()

        logger.info(
            "PLAY REQUEST chat=%s path=%s video=%s",
            chat_id,
            path,
            video,
        )

        if not path.exists():
            logger.error(
                "PLAY FAILED: file does not exist: %s",
                path,
            )
            return False

        if not path.is_file():
            logger.error(
                "PLAY FAILED: path is not a file: %s",
                path,
            )
            return False

        try:
            size = path.stat().st_size

            logger.info(
                "PLAY FILE chat=%s size=%s bytes suffix=%s",
                chat_id,
                size,
                path.suffix,
            )

            if size <= 0:
                logger.error(
                    "PLAY FAILED: empty file: %s",
                    path,
                )
                return False

        except Exception:
            logger.exception(
                "PLAY FAILED: unable to inspect file."
            )
            return False

        async with self._lock(chat_id):

            try:
                # ---------------------------------------------
                # IMPORTANT:
                # Stop any previous stream first.
                # ---------------------------------------------

                if chat_id in self.current_streams:

                    logger.info(
                        "Stopping previous stream before new playback: %s",
                        chat_id,
                    )

                    try:
                        result = self.calls.leave_call(chat_id)

                        if hasattr(result, "__await__"):
                            await result

                    except Exception:
                        logger.debug(
                            "Previous call cleanup failed.",
                            exc_info=True,
                        )

                    self.current_streams.pop(
                        chat_id,
                        None,
                    )

                    self.current_media.pop(
                        chat_id,
                        None,
                    )

                    await asyncio.sleep(0.3)

                # ---------------------------------------------
                # AUDIO ONLY
                # ---------------------------------------------

                logger.info(
                    "Creating MediaStream for chat=%s",
                    chat_id,
                )

                if video:
                    stream = MediaStream(
                        str(path),
                    )
                else:
                    try:
                        stream = MediaStream(
                            str(path),
                            video_flags=MediaStream.Flags.IGNORE,
                        )
                    except Exception:
                        logger.warning(
                            "Audio MediaStream Flags.IGNORE unavailable; "
                            "using basic MediaStream.",
                            exc_info=True,
                        )

                        stream = MediaStream(
                            str(path),
                        )

                logger.info(
                    "MediaStream created successfully for chat=%s",
                    chat_id,
                )

                # ---------------------------------------------
                # PLAY
                # ---------------------------------------------

                logger.info(
                    "Calling PyTgCalls.play(chat=%s)...",
                    chat_id,
                )

                result = self.calls.play(
                    chat_id,
                    stream,
                )

                if hasattr(result, "__await__"):
                    await result

                logger.info(
                    "PyTgCalls.play() returned successfully for chat=%s",
                    chat_id,
                )

                self.current_streams[chat_id] = str(path)
                self.current_media[chat_id] = (
                    "video" if video else "audio"
                )
                self.connected_chats.add(chat_id)

                logger.info(
                    "MUSIC PLAYING SUCCESS chat=%s file=%s",
                    chat_id,
                    path,
                )

                return True

            except Exception as exc:

                logger.exception(
                    "!!! PYTGCALLS PLAYBACK FAILED !!! "
                    "chat=%s file=%s error=%r",
                    chat_id,
                    path,
                    exc,
                )

                self.current_streams.pop(
                    chat_id,
                    None,
                )

                self.current_media.pop(
                    chat_id,
                    None,
                )

                return False

    async def stop(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        try:
            result = self.calls.leave_call(chat_id)

            if hasattr(result, "__await__"):
                await result

            logger.info(
                "VC playback stopped for chat %s",
                chat_id,
            )

            success = True

        except Exception as exc:

            logger.warning(
                "VC stop failed for %s: %s",
                chat_id,
                exc,
            )

            success = False

        finally:
            self.current_streams.pop(
                chat_id,
                None,
            )

            self.current_media.pop(
                chat_id,
                None,
            )

            self.connected_chats.discard(
                chat_id,
            )

        return success

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        try:
            result = self.calls.pause(
                int(chat_id),
            )

            if hasattr(result, "__await__"):
                await result

            logger.info(
                "Paused media in VC %s",
                chat_id,
            )

            return True

        except Exception:
            logger.exception(
                "Failed pausing media in VC %s",
                chat_id,
            )
            return False

    async def resume(
        self,
        chat_id: int,
    ) -> bool:

        try:
            result = self.calls.resume(
                int(chat_id),
            )

            if hasattr(result, "__await__"):
                await result

            logger.info(
                "Resumed media in VC %s",
                chat_id,
            )

            return True

        except Exception:
            logger.exception(
                "Failed resuming media in VC %s",
                chat_id,
            )
            return False

    async def change_stream(
        self,
        chat_id: int,
        media_path: str,
        *,
        video: bool = False,
    ) -> bool:

        await self.stop(chat_id)

        await asyncio.sleep(0.5)

        return await self.play(
            chat_id,
            media_path,
            video=video,
        )

    def is_playing(
        self,
        chat_id: int,
    ) -> bool:
        return int(chat_id) in self.current_streams

    def is_connected(
        self,
        chat_id: int,
    ) -> bool:
        return int(chat_id) in self.connected_chats

    def get_current_stream(
        self,
        chat_id: int,
    ) -> Optional[str]:
        return self.current_streams.get(
            int(chat_id),
        )

    def get_current_media_type(
        self,
        chat_id: int,
    ) -> Optional[str]:
        return self.current_media.get(
            int(chat_id),
        )

    async def leave(
        self,
        chat_id: int,
    ) -> bool:
        return await self.stop(chat_id)

    async def cleanup(self) -> None:

        chat_ids = set(
            self.current_streams.keys()
        )

        chat_ids.update(
            self.connected_chats
        )

        for chat_id in list(chat_ids):
            try:
                await self.stop(chat_id)
            except Exception:
                logger.exception(
                    "Failed cleaning VC %s",
                    chat_id,
                )

        self.current_streams.clear()
        self.current_media.clear()
        self.connected_chats.clear()
        self._locks.clear()

        logger.info(
            "AudioStream cleanup completed."
        )


__all__ = ["AudioStream"]
