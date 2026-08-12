import asyncio
import logging
import os
from typing import Optional

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

logger = logging.getLogger(__name__)


class AudioStream:
    """
    Zara Telegram VC audio engine.

    The actual VC connection is created by PyTgCalls when media
    is played. This class keeps playback state synchronized.
    """

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

    # ========================================================
    # INTERNAL
    # ========================================================

    def _lock(self, chat_id: int) -> asyncio.Lock:
        chat_id = int(chat_id)
        return self._locks.setdefault(
            chat_id,
            asyncio.Lock(),
        )

    # ========================================================
    # START
    # ========================================================

    async def start(self) -> None:
        """
        Start PyTgCalls.
        """

        try:
            if hasattr(self.calls, "start"):
                result = self.calls.start()

                if hasattr(result, "__await__"):
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

    async def join(
        self,
        chat_id: int,
    ) -> bool:
        """
        Prepare the chat for playback.

        PyTgCalls will establish the actual media connection
        when play() is called.
        """

        chat_id = int(chat_id)

        self.connected_chats.add(
            chat_id
        )

        logger.info(
            "VC playback ready for chat %s",
            chat_id,
        )

        return True

    async def join_and_record(
        self,
        chat_id: int,
    ) -> bool:
        """
        Backward-compatible alias used by older code.
        """

        return await self.join(
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
        """
        Play local audio/video media in Telegram VC.

        IMPORTANT:
        PyTgCalls MediaStream itself is responsible for creating
        the actual media call when play() is invoked.
        """

        chat_id = int(chat_id)

        if not media_path:
            logger.error(
                "Cannot play: media path is empty."
            )
            return False

        media_path = os.path.abspath(
            str(media_path)
        )

        if not os.path.isfile(media_path):
            logger.error(
                "Cannot play: file does not exist: %s",
                media_path,
            )
            return False

        if os.path.getsize(media_path) <= 0:
            logger.error(
                "Cannot play: media file is empty: %s",
                media_path,
            )
            return False

        async with self._lock(chat_id):

            try:
                logger.info(
                    "Starting VC playback: chat=%s file=%s video=%s",
                    chat_id,
                    media_path,
                    video,
                )

                # ------------------------------------------------
                # Stop previous stream if one exists.
                # ------------------------------------------------

                if chat_id in self.current_streams:
                    try:
                        await self.calls.leave_call(
                            chat_id
                        )
                    except Exception:
                        logger.debug(
                            "Could not leave previous stream in %s",
                            chat_id,
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

                    await asyncio.sleep(
                        0.25
                    )

                # ------------------------------------------------
                # Create MediaStream.
                # ------------------------------------------------

                stream = MediaStream(
                    media_path
                )

                # ------------------------------------------------
                # Start playback.
                # ------------------------------------------------

                result = self.calls.play(
                    chat_id,
                    stream,
                )

                if hasattr(result, "__await__"):
                    await result

                # ------------------------------------------------
                # Save state only after successful play call.
                # ------------------------------------------------

                self.connected_chats.add(
                    chat_id
                )

                self.current_streams[
                    chat_id
                ] = media_path

                self.current_media[
                    chat_id
                ] = (
                    "video"
                    if video
                    else "audio"
                )

                logger.info(
                    "VC playback started successfully: chat=%s media=%s",
                    chat_id,
                    "video" if video else "audio",
                )

                return True

            except Exception:
                logger.exception(
                    "Failed to play media in VC %s: %s",
                    chat_id,
                    media_path,
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

    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
        chat_id: int,
    ) -> bool:
        """
        Stop playback and leave VC.
        """

        chat_id = int(chat_id)

        try:
            await self.calls.leave_call(
                chat_id
            )

            success = True

        except Exception:
            logger.debug(
                "VC leave failed or call was already gone: %s",
                chat_id,
                exc_info=True,
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

        logger.info(
            "VC playback stopped for chat %s",
            chat_id,
        )

        return success

    # ========================================================
    # STOP RECORDING
    # ========================================================

    async def stop_recording(
        self,
        chat_id: int,
    ) -> None:
        self.connected_chats.discard(
            int(chat_id)
        )

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

        return (
            int(chat_id)
            in self.current_streams
        )

    def is_connected(
        self,
        chat_id: int,
    ) -> bool:

        return (
            int(chat_id)
            in self.connected_chats
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

        await self.stop(
            chat_id
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

        for chat_id in list(chat_ids):

            try:
                await self.calls.leave_call(
                    int(chat_id)
                )
            except Exception:
                logger.debug(
                    "Failed cleaning VC %s",
                    chat_id,
                    exc_info=True,
                )

        self.current_streams.clear()
        self.current_media.clear()
        self.connected_chats.clear()
        self._locks.clear()

        logger.info(
            "AudioStream cleanup completed."
        )


__all__ = ["AudioStream"]
