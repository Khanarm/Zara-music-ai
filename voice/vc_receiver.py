# voice/vc_receiver.py

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
    Compatible VC manager for the current PyTgCalls API.

    Responsibilities:
        - Join active Telegram voice chats.
        - Leave voice chats.
        - Track joined chats.
        - Register optional speech-frame listener if the
          installed PyTgCalls version provides it.
        - Never break the complete music system when speech
          capture is unavailable.
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

    # ========================================================
    # REGISTER
    # ========================================================

    async def register(self) -> bool:
        """
        Register optional incoming speech capture.

        Newer PyTgCalls versions may not expose the old
        filters.stream_frame() API. In that case we keep
        VC join/music functionality enabled and simply
        disable speech capture.
        """

        if self._registered:
            return self._speech_capture_available

        self._registered = True

        try:

            from pytgcalls import filters as pytg_filters

        except Exception:

            logger.warning(
                "PyTgCalls filters API unavailable. "
                "VC speech capture disabled."
            )

            return False

        stream_frame = getattr(
            pytg_filters,
            "stream_frame",
            None,
        )

        if stream_frame is None:

            logger.warning(
                "PyTgCalls does not provide "
                "filters.stream_frame(). "
                "VC speech frame capture is unavailable."
            )

            return False

        # ----------------------------------------------------
        # Try registering the old stream-frame API.
        # ----------------------------------------------------

        try:

            decorator = self.calls.on_update(
                stream_frame()
            )

            if decorator is None:

                logger.warning(
                    "PyTgCalls stream-frame registration "
                    "returned no decorator."
                )

                return False

            async def handler(
                client,
                update,
            ):

                await self._handle_stream_frame(
                    update
                )

            decorator(handler)

            self._speech_capture_available = True

            logger.info(
                "VC speech frame capture registered."
            )

            return True

        except Exception:

            logger.warning(
                "Installed PyTgCalls stream-frame API "
                "is not compatible with VC receiver. "
                "Speech capture disabled.",
                exc_info=True,
            )

            self._speech_capture_available = False

            return False

    # ========================================================
    # HANDLE STREAM FRAME
    # ========================================================

    async def _handle_stream_frame(
        self,
        update,
    ) -> None:

        """
        Optional frame callback.

        This is intentionally defensive because PyTgCalls
        versions expose different frame objects.
        """

        if not self.on_transcript:
            return

        try:

            chat_id = getattr(
                update,
                "chat_id",
                None,
            )

            if chat_id is None:
                return

            # The current project does not include a guaranteed
            # STT decoder for arbitrary PyTgCalls frames here.
            #
            # Keep this method ready for a future compatible
            # frame decoder without breaking VC joining.

            return

        except Exception:

            logger.exception(
                "Failed to process VC stream frame."
            )

    # ========================================================
    # CHECK ACTIVE VC
    # ========================================================

    async def has_active_voice_chat(
        self,
        chat_id: int,
    ) -> bool:

        """
        Check whether Telegram currently has an active
        group call for this chat.
        """

        try:

            # Current PyTgCalls exposes get_input_call()
            # through its MTProto client internally, but the
            # public high-level API may vary between versions.

            app = getattr(
                self.calls,
                "mtproto_client",
                None,
            )

            if app is not None:

                getter = getattr(
                    app,
                    "get_input_call",
                    None,
                )

                if getter is not None:

                    result = getter(chat_id)

                    if inspect.isawaitable(result):
                        result = await result

                    return result is not None

        except Exception:

            logger.debug(
                "Unable to directly inspect active VC.",
                exc_info=True,
            )

        # ----------------------------------------------------
        # Fallback:
        #
        # Let PyTgCalls attempt the join. If there is no
        # active VC, its NoActiveGroupCall exception will
        # be handled by join().
        # ----------------------------------------------------

        return True

    # ========================================================
    # JOIN
    # ========================================================

    async def join(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        # Already connected.
        if chat_id in self.joined_chats:

            logger.info(
                "VC receiver already joined for %s",
                chat_id,
            )

            return True

        try:

            # ------------------------------------------------
            # IMPORTANT:
            #
            # Current PyTgCalls supports:
            #
            # await calls.play(chat_id, None)
            #
            # This creates/connects the group-call transport
            # without requiring an audio file.
            # ------------------------------------------------

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
                    "VC receiver joined logically for %s, "
                    "but incoming speech capture is unavailable "
                    "with the installed PyTgCalls API.",
                    chat_id,
                )

            return True

        except Exception as exc:

            logger.warning(
                "VC join failed for %s: %s",
                chat_id,
                exc,
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

            # If PyTgCalls says we are not in a call,
            # still clean our local state.
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
    # IS JOINED
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

        logger.info(
            "VC receiver cleanup completed."
        )
