# audio/stream.py

import asyncio
import logging
import os
from typing import Optional

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

try:
    from pytgcalls.exceptions import GroupCallNotFoundError
except ImportError:
    GroupCallNotFoundError = Exception


logger = logging.getLogger(__name__)


class AudioStream:
    """
    Zara Telegram Voice Chat media engine.

    Uses the installed PyTgCalls MediaStream API.
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

    # ========================================================
    # START
    # ========================================================

    async def start(self) -> None:
        """Start PyTgCalls."""

        try:
            await self.calls.start()

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
        """
        Prepare Zara for VC usage.

        RecordStream is intentionally NOT used because it is
        unavailable in the installed PyTgCalls version.

        Actual VC connection happens when MediaStream is played.
        """

        chat_id = int(chat_id)

        try:
            if chat_id in self.connected_chats:
                logger.info(
                    "Already connected to VC: %s",
                    chat_id,
                )
                return True

            logger.info(
                "VC ready for chat: %s",
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
        """Clear VC connection state."""

        chat_id = int(chat_id)

        self.connected_chats.discard(
            chat_id
        )

    # ========================================================
    # PLAY AUDIO / VIDEO
    # ========================================================

    async def play(
        self,
        chat_id: int,
        media_path: str,
        *,
        video: bool = False,
    ) -> bool:
        """
        Play an audio or video file in a Telegram VC.
        """

        chat_id = int(chat_id)

        if not media_path:
            logger.error(
                "Media path is empty."
            )
            return False

        if not os.path.isfile(media_path):
            logger.error(
                "Media file does not exist: %s",
                media_path,
            )
            return False

        try:
            # ------------------------------------------------
            # MediaStream
            # ------------------------------------------------

            stream = MediaStream(
                media_path
            )

            # ------------------------------------------------
            # Play
            # ------------------------------------------------

            await self.calls.play(
                chat_id,
                stream,
            )

            # ------------------------------------------------
            # State
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
                "Playing %s in VC %s: %s",
                "video" if video else "audio",
                chat_id,
                media_path,
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
                "Failed playing media in VC %s",
                chat_id,
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
        Stop playback and leave the VC.
        """

        chat_id = int(chat_id)

        try:
            await self.calls.leave_call(
                chat_id
            )

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
                "Left VC: %s",
                chat_id,
            )

            return True

        except GroupCallNotFoundError:
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

            return False

        except Exception:
            logger.exception(
                "Failed stopping VC %s",
                chat_id,
            )
            return False

    # ========================================================
    # PAUSE
    # ========================================================

    async def pause(
        self,
        chat_id: int,
    ) -> bool:
        """Pause current media."""

        chat_id = int(chat_id)

        try:
            await self.calls.pause(
                chat_id
            )

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
        """Resume current media."""

        chat_id = int(chat_id)

        try:
            await self.calls.resume(
                chat_id
            )

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
        """Leave VC."""

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
        """
        Replace the currently playing media.
        """

        chat_id = int(chat_id)

        if self.is_playing(chat_id):

            try:
                await self.calls.leave_call(
                    chat_id
                )

            except Exception:
                logger.debug(
                    "Failed leaving old stream %s",
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

        return await self.play(
            chat_id,
            media_path,
            video=video,
        )

    # ========================================================
    # CLEANUP
    # ========================================================

    async def cleanup(self) -> None:
        """Clean up all active VC sessions."""

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

        logger.info(
            "AudioStream cleanup completed."
    )
