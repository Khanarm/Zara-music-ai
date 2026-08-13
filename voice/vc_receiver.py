import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

TranscriptHandler = Callable[
    [int, str],
    Awaitable[None],
]


class VoiceChatReceiver:
    """
    VC helper for PyTgCalls 2.3.3.

    IMPORTANT:
        PyTgCalls 2.x joins the active group call as part of
        play(chat_id, MediaStream(...)).

        Therefore this class MUST NOT call:
            play(chat_id, None)

        This class only:
            - checks whether an active VC exists
            - tracks chats used by Zara
            - registers incoming stream-frame updates
            - provides leave/status/cleanup helpers
    """

    def __init__(
        self,
        calls,
        user_client=None,
        on_transcript: Optional[TranscriptHandler] = None,
    ) -> None:
        self.calls = calls
        self.user_client = user_client
        self.on_transcript = on_transcript

        self.joined_chats: set[int] = set()

        self._registered = False
        self._speech_capture_available = False

        self._update_types_logged: set[str] = set()

    # ========================================================
    # REGISTER
    # ========================================================

    async def register(self) -> bool:
        """
        Register PyTgCalls stream-frame callback when supported.
        """

        if self._registered:
            return self._speech_capture_available

        self._registered = True

        try:
            from pytgcalls import filters
        except Exception:
            logger.warning(
                "PyTgCalls filters API unavailable."
            )
            return False

        try:
            stream_frame = getattr(
                filters,
                "stream_frame",
                None,
            )

            if stream_frame is None:
                logger.warning(
                    "PyTgCalls does not expose filters.stream_frame()."
                )
                return False

            filter_object = stream_frame()

            decorator = self.calls.on_update(
                filter_object
            )

            if decorator is None:
                logger.warning(
                    "PyTgCalls on_update() returned no decorator."
                )
                return False

            async def frame_handler(
                client,
                update,
            ):
                await self._handle_stream_frame(
                    update
                )

            decorator(frame_handler)

            self._speech_capture_available = True

            logger.info(
                "VC speech frame capture registered."
            )

            return True

        except Exception:
            logger.warning(
                "PyTgCalls stream-frame registration failed.",
                exc_info=True,
            )

            self._speech_capture_available = False
            return False

    # ========================================================
    # ACTIVE VC CHECK
    # ========================================================

    async def has_active_call(
        self,
        chat_id: int,
    ) -> bool:
        """
        Check whether the group currently has an active
        voice/video chat.

        Does NOT create a call.
        """

        chat_id = int(chat_id)

        try:
            group_calls = getattr(
                self.calls,
                "group_calls",
                None,
            )

            if group_calls is None:
                logger.warning(
                    "PyTgCalls group_calls API unavailable."
                )
                return False

            if callable(group_calls):
                result = group_calls()

                if hasattr(result, "__await__"):
                    result = await result

                group_calls = result

            try:
                return chat_id in group_calls
            except Exception:
                pass

        except Exception:
            logger.debug(
                "Could not inspect active group calls.",
                exc_info=True,
            )

        return False

    # ========================================================
    # JOIN / PREPARE
    # ========================================================

    async def join(
        self,
        chat_id: int,
    ) -> bool:
        """
        Prepare Zara for playback.

        NOTE:
        PyTgCalls 2.3.3 performs the actual VC connection when
        play(chat_id, MediaStream(...)) is called.

        Therefore this method only verifies that an active VC
        exists and marks the chat as ready.
        """

        chat_id = int(chat_id)

        if chat_id in self.joined_chats:
            return True

        active = await self.has_active_call(
            chat_id
        )

        if not active:
            logger.warning(
                "No active VC found for %s.",
                chat_id,
            )
            return False

        self.joined_chats.add(
            chat_id
        )

        if not self._registered:
            await self.register()

        logger.info(
            "VC ready for Zara playback: %s",
            chat_id,
        )

        return True

    # ========================================================
    # UPDATE DEBUG
    # ========================================================

    def _log_update_structure(
        self,
        update,
    ) -> None:

        update_type = type(update).__name__

        if update_type in self._update_types_logged:
            return

        self._update_types_logged.add(
            update_type
        )

        try:
            attributes = {}

            for name in dir(update):

                if name.startswith("_"):
                    continue

                try:
                    value = getattr(
                        update,
                        name,
                    )

                    if callable(value):
                        continue

                    if isinstance(value, bytes):
                        attributes[name] = (
                            f"<bytes:{len(value)}>"
                        )
                    else:
                        text = repr(value)

                        if len(text) > 300:
                            text = (
                                text[:300]
                                + "..."
                            )

                        attributes[name] = text

                except Exception:
                    continue

            logger.info(
                "PyTgCalls update detected: %s | attrs=%s",
                update_type,
                attributes,
            )

        except Exception:
            logger.exception(
                "Failed inspecting PyTgCalls update."
            )

    # ========================================================
    # CHAT ID
    # ========================================================

    def _extract_chat_id(
        self,
        update,
    ) -> Optional[int]:

        value = getattr(
            update,
            "chat_id",
            None,
        )

        if value is not None:
            try:
                return int(value)
            except Exception:
                pass

        group_call = getattr(
            update,
            "group_call",
            None,
        )

        if group_call is not None:

            value = getattr(
                group_call,
                "chat_id",
                None,
            )

            if value is not None:
                try:
                    return int(value)
                except Exception:
                    pass

        chat = getattr(
            update,
            "chat",
            None,
        )

        if chat is not None:

            value = getattr(
                chat,
                "id",
                None,
            )

            if value is not None:
                try:
                    return int(value)
                except Exception:
                    pass

        return None

    # ========================================================
    # AUDIO DATA
    # ========================================================

    def _extract_audio_bytes(
        self,
        update,
    ) -> Optional[bytes]:

        possible_names = (
            "frame",
            "data",
            "audio",
            "audio_data",
            "pcm",
            "pcm_data",
            "raw",
            "raw_data",
            "payload",
            "samples",
        )

        for name in possible_names:

            try:
                value = getattr(
                    update,
                    name,
                    None,
                )
            except Exception:
                continue

            if value is None:
                continue

            if isinstance(value, bytes):
                return value

            if isinstance(value, bytearray):
                return bytes(value)

            if isinstance(value, memoryview):
                return value.tobytes()

        return None

    # ========================================================
    # FRAME HANDLER
    # ========================================================

    async def _handle_stream_frame(
        self,
        update,
    ) -> None:

        try:

            self._log_update_structure(
                update
            )

            chat_id = self._extract_chat_id(
                update
            )

            if chat_id is None:
                return

            audio_data = self._extract_audio_bytes(
                update
            )

            if not audio_data:
                return

            logger.debug(
                "Received VC audio frame: chat=%s bytes=%s",
                chat_id,
                len(audio_data),
            )

            # STT buffering can be connected here later.
            # Never send arbitrary individual frames
            # directly to Gemini.

        except Exception:
            logger.exception(
                "Failed to process PyTgCalls stream frame."
            )

    # ========================================================
    # LEAVE
    # ========================================================

    async def leave(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        try:

            leave_call = getattr(
                self.calls,
                "leave_call",
                None,
            )

            if leave_call is None:
                raise RuntimeError(
                    "PyTgCalls leave_call() unavailable."
                )

            result = leave_call(
                chat_id
            )

            if hasattr(result, "__await__"):
                await result

            logger.info(
                "Zara left VC: %s",
                chat_id,
            )

            return True

        except Exception as exc:

            logger.warning(
                "VC leave failed for %s: %s",
                chat_id,
                exc,
            )

            return False

        finally:
            self.joined_chats.discard(
                chat_id
            )

    # ========================================================
    # STATUS
    # ========================================================

    def is_joined(
        self,
        chat_id: int,
    ) -> bool:

        return int(chat_id) in self.joined_chats

    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
        chat_id: Optional[int] = None,
    ) -> None:

        if chat_id is not None:
            await self.leave(
                int(chat_id)
            )
            return

        for current_chat_id in list(
            self.joined_chats
        ):
            await self.leave(
                current_chat_id
            )

    # ========================================================
    # CLEANUP
    # ========================================================

    async def cleanup(self) -> None:

        for chat_id in list(
            self.joined_chats
        ):
            try:
                await self.leave(
                    chat_id
                )
            except Exception:
                logger.exception(
                    "Failed to cleanup VC %s",
                    chat_id,
                )

        self.joined_chats.clear()

        self._registered = False
        self._speech_capture_available = False
        self._update_types_logged.clear()

        logger.info(
            "VC receiver cleanup completed."
        )


__all__ = [
    "VoiceChatReceiver",
    "TranscriptHandler",
]
