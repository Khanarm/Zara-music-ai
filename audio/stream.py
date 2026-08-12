import asyncio
import logging
import os
from typing import Optional

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

try:
    from pytgcalls.exceptions import (
        GroupCallNotFoundError,
    )
except ImportError:
    GroupCallNotFoundError = Exception


logger = logging.getLogger(__name__)


class AudioStream:
    """
    Zara Telegram VC media engine.

    PyTgCalls handles media decoding through FFmpeg.
    Audio files are normalized by MusicDownloader before
    reaching this class.
    """

    def __init__(
        self,
        client,
        calls: PyTgCalls,
    ):
        self.client = client
        self.calls = calls

        self.current_streams: dict[
            int,
            str,
        ] = {}

        self.current_media: dict[
            int,
            str,
        ] = {}

        self.connected_chats: set[int] = set()

        self._play_locks: dict[
            int,
            asyncio.Lock,
        ] = {}

    # ========================================================
    # LOCK
    # ========================================================

    def _lock(
        self,
        chat_id: int,
    ) -> asyncio.Lock:

        chat_id = int(chat_id)

        return self._play_locks.setdefault(
            chat_id,
            asyncio.Lock(),
        )

    # ========================================================
    # START
    # ========================================================

    async def start(self) -> None:

        try:

            result = self.calls.start()

            if hasattr(
                result,
                "__await__",
            ):
                await result

            logger.info(
                "PyTgCalls started successfully."
            )

        except Exception:

            logger.exception(
                "Failed to start PyTgCalls."
            )

            raise

    # ========================================================
    # JOIN
    # ========================================================

    async def join_and_record(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        if chat_id in self.connected_chats:
            return True

        try:

            # PyTgCalls 2.x joins the active VC when
            # media is played. There is no need to create
            # a dummy RecordStream here.

            logger.info(
                "VC ready for playback: %s",
                chat_id,
            )

            return True

        except GroupCallNotFoundError:

            logger.warning(
                "No active voice chat in %s",
                chat_id,
            )

            return False

        except Exception:

            logger.exception(
                "Failed preparing VC %s",
                chat_id,
            )

            return False

    # ========================================================
    # STOP RECORDING
    # ========================================================

    async def stop_recording(
        self,
        chat_id: int,
    ) -> None:

        chat_id = int(chat_id)

        self.connected_chats.discard(
            chat_id
        )

    # ========================================================
    # PLAY
    # ========================================================

    async def play(
        self,
        chat_id: int,
        media_path: str,
        *,
        video: bool = False,
    ) -> bool:

        chat_id = int(chat_id)

        if not media_path:

            logger.error(
                "Playback rejected: empty media path."
            )

            return False

        path = os.path.abspath(
            str(media_path)
        )

        if not os.path.isfile(path):

            logger.error(
                "Playback rejected: file does not exist: %s",
                path,
            )

            return False

        try:

            size = os.path.getsize(
                path
            )

            if size <= 0:

                logger.error(
                    "Playback rejected: empty media file: %s",
                    path,
                )

                return False

        except OSError:

            logger.exception(
                "Could not inspect media file: %s",
                path,
            )

            return False

        async with self._lock(
            chat_id
        ):

            try:

                logger.info(
                    "Starting playback chat=%s file=%s "
                    "size=%s video=%s",
                    chat_id,
                    path,
                    size,
                    video,
                )

                # ------------------------------------------------
                # Explicitly disable video for normal music.
                # ------------------------------------------------

                if video:

                    stream = MediaStream(
                        path
                    )

                else:

                    try:

                        stream = MediaStream(
                            path,
                            video_flags=MediaStream.Flags.IGNORE,
                        )

                    except (
                        TypeError,
                        AttributeError,
                    ):

                        # Compatibility fallback for versions
                        # where Flags.IGNORE is unavailable.
                        stream = MediaStream(
                            path
                        )

                result = self.calls.play(
                    chat_id,
                    stream,
                )

                if hasattr(
                    result,
                    "__await__",
                ):
                    await result

                self.connected_chats.add(
                    chat_id
                )

                self.current_streams[
                    chat_id
                ] = path

                self.current_media[
                    chat_id
                ] = (
                    "video"
                    if video
                    else "audio"
                )

                logger.info(
                    "Playback started successfully "
                    "in VC %s: %s",
                    chat_id,
                    path,
                )

                return True

            except GroupCallNotFoundError:

                logger.warning(
                    "No active voice chat found "
                    "while playing in %s",
                    chat_id,
                )

                return False

            except Exception:

                logger.exception(
                    "PyTgCalls playback failed "
                    "chat=%s file=%s",
                    chat_id,
                    path,
                )

                return False

    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        try:

            result = self.calls.leave_call(
                chat_id
            )

            if hasattr(
                result,
                "__await__",
            ):
                await result

            logger.info(
                "Left VC: %s",
                chat_id,
            )

            success = True

        except GroupCallNotFoundError:

            success = False

        except Exception:

            logger.exception(
                "Failed stopping VC %s",
                chat_id,
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
                chat_id
            )

        return success

    # ========================================================
    # PAUSE
    # ========================================================

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        try:

            result = self.calls.pause(
                chat_id
            )

            if hasattr(
                result,
                "__await__",
            ):
                await result

            logger.info(
                "Paused media in VC %s",
                chat_id,
            )

            return True

        except Exception:

            logger.exception(
                "Failed pausing media in %s",
                chat_id,
            )

            return False

    # ========================================================
    # RESUME
    # ========================================================

    async def resume(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        try:

            result = self.calls.resume(
                chat_id
            )

            if hasattr(
                result,
                "__await__",
            ):
                await result

            logger.info(
                "Resumed media in VC %s",
                chat_id,
            )

            return True

        except Exception:

            logger.exception(
                "Failed resuming media in %s",
                chat_id,
            )

            return False

    # ========================================================
    # LEAVE
    # ========================================================

    async def leave(
        self,
        chat_id: int,
    ) -> bool:

        return await self.stop(
            chat_id
        )

    # ========================================================
    # STATUS
    # ========================================================

    def is_playing(
        self,
        chat_id: int,
    ) -> bool:

        return int(chat_id) in (
            self.current_streams
        )

    def is_connected(
        self,
        chat_id: int,
    ) -> bool:

        return int(chat_id) in (
            self.connected_chats
        )

    def get_current_stream(
        self,
        chat_id: int,
    ) -> Optional[str]:

        return self.current_streams.get(
            int(chat_id)
        )

    def get_current_media_type(
        self,
        chat_id: int,
    ) -> Optional[str]:

        return self.current_media.get(
            int(chat_id)
        )

    # ========================================================
    # CHANGE STREAM
    # ========================================================

    async def change_stream(
        self,
        chat_id: int,
        media_path: str,
        *,
        video: bool = False,
    ) -> bool:

        chat_id = int(chat_id)

        if self.is_playing(
            chat_id
        ):

            try:

                await self.stop(
                    chat_id
                )

            except Exception:

                logger.exception(
                    "Failed stopping old stream "
                    "before changing stream."
                )

            await asyncio.sleep(
                0.25
            )

        return await self.play(
            chat_id,
            media_path,
            video=video,
        )

    # ========================================================
    # CLEANUP
    # ========================================================

    async def cleanup(self) -> None:

        chat_ids = set(
            self.current_streams.keys()
        )

        chat_ids.update(
            self.connected_chats
        )

        for chat_id in list(
            chat_ids
        ):

            try:

                await self.stop(
                    chat_id
                )

            except Exception:

                logger.exception(
                    "Failed cleaning VC %s",
                    chat_id,
                )

        self.current_streams.clear()
        self.current_media.clear()
        self.connected_chats.clear()
        self._play_locks.clear()

        logger.info(
            "AudioStream cleanup completed."
        )


__all__ = [
    "AudioStream",
        ]
