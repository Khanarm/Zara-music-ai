import inspect
import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

TranscriptHandler = Callable[
    [int, str],
    Awaitable[None],
]


class VoiceChatReceiver:
    """
    Safe Telegram VC receiver for the installed PyTgCalls version.

    Responsibilities:
        - Join an active Telegram voice chat.
        - Leave a voice chat.
        - Track joined chats.
        - Register compatible PyTgCalls stream callbacks when available.
        - NEVER assume that every PyTgCalls update has chat_id.
        - Log the actual update structure for debugging.
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

        # Prevent log spam.
        self._update_types_logged: set[str] = set()

    # ========================================================
    # REGISTER
    # ========================================================

    async def register(self) -> bool:
        """
        Try to register the stream-frame API if the installed
        PyTgCalls version exposes it.

        This function does NOT assume the callback contains
        chat_id or audio bytes.
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

        try:
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
    # UPDATE DEBUG
    # ========================================================

    def _log_update_structure(
        self,
        update,
    ) -> None:
        """
        Log the real structure of the PyTgCalls update.

        This intentionally avoids assuming chat_id exists.
        """

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
                    value = getattr(update, name)

                    if callable(value):
                        continue

                    # Avoid dumping huge byte buffers.
                    if isinstance(value, bytes):
                        attributes[name] = (
                            f"<bytes:{len(value)}>"
                        )
                    else:
                        text = repr(value)

                        if len(text) > 300:
                            text = text[:300] + "..."

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
    # GET CHAT ID
    # ========================================================

    def _extract_chat_id(
        self,
        update,
    ) -> Optional[int]:
        """
        Safely extract chat ID from different possible
        PyTgCalls update objects.
        """

        # Direct chat_id.
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

        # Some update objects may expose group_call.
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

        # Some objects may expose chat.
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
    # EXTRACT AUDIO
    # ========================================================

    def _extract_audio_bytes(
        self,
        update,
    ) -> Optional[bytes]:
        """
        Try common attribute names for incoming PCM/audio data.

        We deliberately do NOT pretend an arbitrary field is
        audio unless it is actually bytes-like.
        """

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
    # HANDLE STREAM FRAME
    # ========================================================

    async def _handle_stream_frame(
        self,
        update,
    ) -> None:
        """
        Handle an incoming PyTgCalls update safely.

        At this stage we only accept a real bytes-like audio
        payload. No fake transcription is generated.
        """

        try:
            self._log_update_structure(
                update
            )

            chat_id = self._extract_chat_id(
                update
            )

            if chat_id is None:
                logger.debug(
                    "PyTgCalls update has no resolvable chat ID: %s",
                    type(update).__name__,
                )
                return

            audio_data = self._extract_audio_bytes(
                update
            )

            if audio_data is None:
                logger.debug(
                    "No audio bytes found in PyTgCalls update for %s.",
                    chat_id,
                )
                return

            if not audio_data:
                return

            logger.debug(
                "Received VC audio data: chat=%s bytes=%s",
                chat_id,
                len(audio_data),
            )

            # IMPORTANT:
            #
            # Do not send arbitrary raw frames directly to Gemini.
            # A proper buffering/segmentation layer is required.
            #
            # The actual PCM stream format exposed by the installed
            # PyTgCalls build must first be confirmed.
            #
            # Therefore this receiver currently only verifies that
            # audio bytes are actually arriving.

        except Exception:
            logger.exception(
                "Failed to process PyTgCalls stream frame."
            )

    # ========================================================
    # JOIN
    # ========================================================

    async def join(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        if chat_id in self.joined_chats:
            logger.info(
                "VC receiver already joined for %s",
                chat_id,
            )
            return True

        try:
            play = getattr(
                self.calls,
                "play",
                None,
            )

            if play is None:
                raise RuntimeError(
                    "Installed PyTgCalls does not expose play()."
                )

            result = play(
                chat_id,
                None,
            )

            if inspect.isawaitable(result):
                await result

            self.joined_chats.add(
                chat_id
            )

            logger.info(
                "VC receiver joined successfully for %s",
                chat_id,
            )

            if not self._registered:
                await self.register()

            if self._speech_capture_available:
                logger.info(
                    "VC speech capture enabled for %s",
                    chat_id,
                )
            else:
                logger.warning(
                    "VC joined, but compatible speech-frame "
                    "capture is unavailable for %s.",
                    chat_id,
                )

            return True

        except Exception as exc:

            logger.exception(
                "VC join failed for %s: %s",
                chat_id,
                exc,
            )

            self.joined_chats.discard(
                chat_id
            )

            return False

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
                    "Installed PyTgCalls does not expose leave_call()."
                )

            result = leave_call(
                chat_id
            )

            if inspect.isawaitable(result):
                await result

            self.joined_chats.discard(
                chat_id
            )

            logger.info(
                "VC speech receiver stopped for chat %s",
                chat_id,
            )

            return True

        except Exception as exc:

            self.joined_chats.discard(
                chat_id
            )

            logger.warning(
                "VC leave failed for %s: %s",
                chat_id,
                exc,
            )

            return False

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
