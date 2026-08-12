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
    Telegram VC media engine for Zara.

    Compatible with the current PyTgCalls MediaStream API.

    Responsibilities:
        - Play audio
        - Play video
        - Pause
        - Resume
        - Stop
        - Leave VC
        - Track currently playing media
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
        """
        Start PyTgCalls.
        """

        try:
            await self.calls.start()
            logger.info("PyTgCalls started successfully")

        except Exception:
            logger.exception(
                "Failed to start PyTgCalls"
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
        Join an active Telegram voice chat.

        NOTE:
        The old RecordStream based implementation is removed
        because RecordStream is not available in the installed
        PyTgCalls version.

        If the project needs microphone/input capture later,
        that will be implemented separately using the correct
        PyTgCalls receiver API.
        """

        chat_id = int(chat_id)

        try:
            # If already connected, nothing to do.
            if chat_id in self.connected_chats:
                logger.info(
                    "Already connected to VC: %s",
                    chat_id,
                )
                return True

            # PyTgCalls joins the voice chat when a media stream
            # is played. There is no RecordStream here.
            #
            # Do NOT call:
            #   self.calls.record(...)
            #
            # because RecordStream does not exist in the
            # installed PyTgCalls package.

            logger.info(
                "Preparing Zara VC connection for %s",
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
                "Failed preparing VC connection %s",
                chat_id,
            )
            return False

    # ========================================================
    # STOP RECORDING / CONNECTION STATE
    # ========================================================

    async def stop_recording(
        self,
        chat_id: int,
    ) -> None:
        """
        Stop receiver/recording state.

        Kept for compatibility with existing callers.
        """

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
        """
        Play an audio or video file in Telegram VC.
        """

        chat_id = int(chat_id)

        if not media_path:
            logger.error(
                "Media path is empty"
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
            # Build MediaStream
            # ------------------------------------------------

            if video:
                stream = MediaStream(
                    media_path,
                )

                media_type = "video"

            else:
                stream = MediaStream(
                    media_path,
                )

                media_type = "audio"

            # ------------------------------------------------
            # Start playback
            # ------------------------------------------------

            await self.calls.play(
                chat_id,
                stream,
            )

            self.connected_chats.add(
                chat_id
            )

            self.current_streams[
                chat_id
            ] = media_path

            self.current_media[
                chat_id
            ] = media_type

            logger.info(
                "Started %s playback in %s: %s",
                media_type,
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
                "Failed playing media in %s",
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
        Stop current playback.

        Zara remains connected only if another component
        manages the VC connection separately.
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
                "Stopped VC stream and left %s",
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
                "Failed stopping stream in %s",
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
        """
        Pause current media.
        """

        chat_id = int(chat_id)

        try:
            await self.calls.pause(
                chat_id
            )

            logger.info(
                "Paused stream in %s",
                chat_id,
            )

            return True

        except Exception:
            logger.exception(
                "Failed pausing stream in %s",
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
        """
        Resume current media.
        """

        chat_id = int(chat_id)

        try:
            await self.calls.resume(
                chat_id
            )

            logger.info(
                "Resumed stream in %s",
                chat_id,
            )

            return True

        except Exception:
            logger.exception(
                "Failed resuming stream in %s",
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
        """
        Leave Telegram VC.
        """

        return await self.stop(
            chat_id
        )

    # ========================================================
    # STATE
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
        Change currently playing media.
        """

        chat_id = int(chat_id)

        if self.is_playing(chat_id):
            try:
                await self.calls.leave_call(
                    chat_id
                )
            except Exception:
                logger.debug(
                    "Could not leave previous stream %s",
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
        """
        Clean up all active streams.
        """

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
            "AudioStream cleanup completed"
            )
