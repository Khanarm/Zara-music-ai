import asyncio
import logging
from pathlib import Path
from typing import Optional

from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

logger = logging.getLogger(__name__)


class AudioStream:
    """
    Actual Zara VC playback engine.

    PyTgCalls 2.3.3:
        play(chat_id, MediaStream(...))

    This call establishes the media connection and starts
    playback in the active Telegram VC.
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

    def _lock(
        self,
        chat_id: int,
    ) -> asyncio.Lock:

        return self._locks.setdefault(
            int(chat_id),
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
    # ACTIVE VC
    # ========================================================

    async def _has_active_call(
        self,
        chat_id: int,
    ) -> bool:

        try:

            group_calls = getattr(
                self.calls,
                "group_calls",
                None,
            )

            if group_calls is None:
                return True

            if callable(group_calls):

                result = group_calls()

                if hasattr(
                    result,
                    "__await__",
                ):
                    result = await result

                group_calls = result

            return int(chat_id) in group_calls

        except Exception:

            # Do not block playback solely because the
            # inspection API is unavailable.
            logger.debug(
                "Active VC inspection unavailable.",
                exc_info=True,
            )

            return True

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
                "PLAY FAILED: empty media path."
            )

            return False

        path = Path(
            media_path
        ).resolve()

        logger.info(
            "PLAY REQUEST chat=%s path=%s video=%s",
            chat_id,
            path,
            video,
        )

        # ----------------------------------------------------
        # File validation
        # ----------------------------------------------------

        if not path.exists():

            logger.error(
                "PLAY FAILED: file does not exist: %s",
                path,
            )

            return False

        if not path.is_file():

            logger.error(
                "PLAY FAILED: not a file: %s",
                path,
            )

            return False

        try:

            size = path.stat().st_size

            if size <= 0:

                logger.error(
                    "PLAY FAILED: empty file: %s",
                    path,
                )

                return False

            logger.info(
                "PLAY FILE chat=%s size=%s suffix=%s",
                chat_id,
                size,
                path.suffix,
            )

        except Exception:

            logger.exception(
                "PLAY FAILED: unable to inspect file."
            )

            return False

        # ----------------------------------------------------
        # Active VC check
        # ----------------------------------------------------

        if not await self._has_active_call(
            chat_id
        ):

            logger.error(
                "PLAY FAILED: no active Voice Chat: %s",
                chat_id,
            )

            return False

        async with self._lock(
            chat_id
        ):

            try:

                # ------------------------------------------------
                # Stop previous media
                # ------------------------------------------------

                if chat_id in self.current_streams:

                    logger.info(
                        "Stopping previous stream: %s",
                        chat_id,
                    )

                    try:

                        result = self.calls.leave_call(
                            chat_id
                        )

                        if hasattr(
                            result,
                            "__await__",
                        ):
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

                    self.connected_chats.discard(
                        chat_id
                    )

                    await asyncio.sleep(
                        0.25
                    )

                # ------------------------------------------------
                # CREATE MEDIA STREAM
                # ------------------------------------------------

                if video:

                    logger.info(
                        "Creating VIDEO MediaStream: %s",
                        path,
                    )

                    stream = MediaStream(
                        str(path)
                    )

                else:

                    logger.info(
                        "Creating AUDIO MediaStream: %s",
                        path,
                    )

                    try:

                        stream = MediaStream(
                            str(path),
                            video_flags=(
                                MediaStream.Flags.IGNORE
                            ),
                        )

                    except Exception:

                        logger.debug(
                            "Audio-only MediaStream flag unavailable; "
                            "using normal MediaStream.",
                            exc_info=True,
                        )

                        stream = MediaStream(
                            str(path)
                        )

                # ------------------------------------------------
                # ACTUAL JOIN + PLAY
                # ------------------------------------------------

                logger.info(
                    "Starting PyTgCalls playback: "
                    "chat=%s video=%s file=%s",
                    chat_id,
                    video,
                    path,
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

                # ------------------------------------------------
                # SUCCESS
                # ------------------------------------------------

                self.current_streams[
                    chat_id
                ] = str(path)

                self.current_media[
                    chat_id
                ] = (
                    "video"
                    if video
                    else "audio"
                )

                self.connected_chats.add(
                    chat_id
                )

                logger.info(
                    "================================================"
                )

                logger.info(
                    "MUSIC PLAYING SUCCESS"
                )

                logger.info(
                    "chat=%s",
                    chat_id,
                )

                logger.info(
                    "media=%s",
                    "video" if video else "audio",
                )

                logger.info(
                    "file=%s",
                    path,
                )

                logger.info(
                    "================================================"
                )

                return True

            except Exception as exc:

                logger.exception(
                    "PYTGCALLS PLAYBACK FAILED "
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

                self.connected_chats.discard(
                    chat_id
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
                "VC playback stopped: %s",
                chat_id,
            )

            return True

        except Exception as exc:

            logger.warning(
                "VC stop failed for %s: %s",
                chat_id,
                exc,
            )

            return False

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

    # ========================================================
    # PAUSE
    # ========================================================

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        try:

            result = self.calls.pause(
                int(chat_id)
            )

            if hasattr(
                result,
                "__await__",
            ):
                await result

            logger.info(
                "Paused VC media: %s",
                chat_id,
            )

            return True

        except Exception:

            logger.exception(
                "Failed pausing VC media: %s",
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

        try:

            result = self.calls.resume(
                int(chat_id)
            )

            if hasattr(
                result,
                "__await__",
            ):
                await result

            logger.info(
                "Resumed VC media: %s",
                chat_id,
            )

            return True

        except Exception:

            logger.exception(
                "Failed resuming VC media: %s",
                chat_id,
            )

            return False

    # ========================================================
    # CHANGE
    # ========================================================

    async def change_stream(
        self,
        chat_id: int,
        media_path: str,
        *,
        video: bool = False,
    ) -> bool:

        await self.stop(
            chat_id
        )

        await asyncio.sleep(
            0.4
        )

        return await self.play(
            chat_id,
            media_path,
            video=video,
        )

    # ========================================================
    # STATE
    # ========================================================

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
            int(chat_id)
        )

    def get_current_media_type(
        self,
        chat_id: int,
    ) -> Optional[str]:

        return self.current_media.get(
            int(chat_id)
        )

    async def leave(
        self,
        chat_id: int,
    ) -> bool:

        return await self.stop(
            chat_id
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
        self._locks.clear()

        logger.info(
            "AudioStream cleanup completed."
        )


__all__ = [
    "AudioStream",
]
