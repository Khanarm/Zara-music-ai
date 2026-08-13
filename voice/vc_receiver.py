# voice/vc_receiver.py

import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


TranscriptHandler = Callable[
    [int, str],
    Awaitable[None],
]


class VoiceChatReceiver:
    """
    Zara Voice Chat receiver/helper.

    PyTgCalls 2.3.3:
        - Active VC is checked through Telethon.
        - Actual PyTgCalls connection happens when
          AudioStream.play() starts playback.
        - This class does NOT call play(chat_id, None).

    Responsibilities:
        - Check whether Zara userbot is inside the group.
        - Detect if Zara is banned.
        - Detect whether an active Telegram VC exists.
        - Prepare chat for PyTgCalls playback.
        - Register stream-frame callbacks when available.
        - Leave VC.
        - Cleanup.
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

        # Last join failure reason.
        #
        # Possible values:
        #   None
        #   "not_in_group"
        #   "banned"
        #   "no_active_call"
        #   "permission_denied"
        #   "not_authorized"
        #   "unavailable"
        #   "join_failed"
        #
        self.last_join_error: dict[
            int,
            str,
        ] = {}

    # ========================================================
    # ERROR STATE
    # ========================================================

    def _set_join_error(
        self,
        chat_id: int,
        reason: str,
    ) -> None:

        self.last_join_error[
            int(chat_id)
        ] = reason

        logger.warning(
            "VC join error: chat=%s reason=%s",
            chat_id,
            reason,
        )

    def get_join_error(
        self,
        chat_id: int,
    ) -> Optional[str]:

        return self.last_join_error.get(
            int(chat_id)
        )

    def clear_join_error(
        self,
        chat_id: int,
    ) -> None:

        self.last_join_error.pop(
            int(chat_id),
            None,
        )

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
                    "PyTgCalls does not expose "
                    "filters.stream_frame()."
                )

                return False

            filter_object = stream_frame()

            decorator = self.calls.on_update(
                filter_object
            )

            if decorator is None:

                logger.warning(
                    "PyTgCalls on_update() returned "
                    "no decorator."
                )

                return False

            async def frame_handler(
                client,
                update,
            ):

                await self._handle_stream_frame(
                    update
                )

            decorator(
                frame_handler
            )

            self._speech_capture_available = True

            logger.info(
                "VC speech frame capture registered."
            )

            return True

        except Exception:

            logger.warning(
                "PyTgCalls stream-frame registration "
                "failed.",
                exc_info=True,
            )

            self._speech_capture_available = False

            return False

    # ========================================================
    # TELETHON GROUP ACCESS
    # ========================================================

    async def _get_self_entity(
        self,
    ):
        """
        Return the logged-in Zara Telethon account.
        """

        if self.user_client is None:
            return None

        try:

            return await self.user_client.get_me()

        except Exception:

            logger.exception(
                "Could not get Zara Telethon account."
            )

            return None

    async def _check_group_membership(
        self,
        chat_id: int,
    ) -> str:
        """
        Check Zara's membership/access.

        Returns:
            "ok"
            "not_in_group"
            "banned"
            "permission_denied"
            "not_authorized"
            "unavailable"
        """

        if self.user_client is None:

            self._set_join_error(
                chat_id,
                "unavailable",
            )

            return "unavailable"

        try:

            if not self.user_client.is_connected():

                self._set_join_error(
                    chat_id,
                    "unavailable",
                )

                return "unavailable"

            if not await self.user_client.is_user_authorized():

                self._set_join_error(
                    chat_id,
                    "not_authorized",
                )

                return "not_authorized"

        except Exception:

            logger.exception(
                "Could not check Telethon authorization."
            )

            self._set_join_error(
                chat_id,
                "unavailable",
            )

            return "unavailable"

        me = await self._get_self_entity()

        if me is None:

            self._set_join_error(
                chat_id,
                "unavailable",
            )

            return "unavailable"

        try:

            permissions = (
                await self.user_client.get_permissions(
                    chat_id,
                    me,
                )
            )

            # Telethon permission objects expose
            # is_banned for restricted/banned users.
            if getattr(
                permissions,
                "is_banned",
                False,
            ):

                self._set_join_error(
                    chat_id,
                    "banned",
                )

                return "banned"

            return "ok"

        except Exception as exc:

            error_name = type(exc).__name__

            logger.warning(
                "Could not get Zara group permissions: "
                "chat=%s error=%s",
                chat_id,
                error_name,
            )

            # These errors generally mean the account
            # is not currently a participant.
            if error_name in {
                "UserNotParticipantError",
                "ChannelPrivateError",
                "ChatAdminRequiredError",
                "ChannelInvalidError",
                "PeerIdInvalidError",
            }:

                self._set_join_error(
                    chat_id,
                    "not_in_group",
                )

                return "not_in_group"

            self._set_join_error(
                chat_id,
                "permission_denied",
            )

            return "permission_denied"

    # ========================================================
    # ACTIVE VC CHECK THROUGH TELETHON
    # ========================================================

    async def has_active_call(
        self,
        chat_id: int,
    ) -> bool:
        """
        Reliably check active Telegram Voice Chat
        through Telethon.

        This does NOT join the call.
        """

        chat_id = int(chat_id)

        if self.user_client is None:

            logger.warning(
                "Telethon client unavailable "
                "while checking active VC: %s",
                chat_id,
            )

            return False

        try:

            entity = await self.user_client.get_entity(
                chat_id
            )

            # ------------------------------------------------
            # SUPERGROUP / CHANNEL
            # ------------------------------------------------

            if getattr(
                entity,
                "broadcast",
                False,
            ) or getattr(
                entity,
                "megagroup",
                False,
            ):

                from telethon.tl.functions.channels import (
                    GetFullChannelRequest,
                )

                full = (
                    await self.user_client(
                        GetFullChannelRequest(
                            entity
                        )
                    )
                )

                call = getattr(
                    full.full_chat,
                    "call",
                    None,
                )

                if call is not None:

                    logger.debug(
                        "Active VC found: %s",
                        chat_id,
                    )

                    return True

                return False

            # ------------------------------------------------
            # NORMAL BASIC GROUP
            # ------------------------------------------------

            from telethon.tl.functions.messages import (
                GetFullChatRequest,
            )

            full = (
                await self.user_client(
                    GetFullChatRequest(
                        entity.id
                    )
                )
            )

            call = getattr(
                full.full_chat,
                "call",
                None,
            )

            if call is not None:

                logger.debug(
                    "Active VC found: %s",
                    chat_id,
                )

                return True

        except Exception:

            logger.debug(
                "Telethon active VC check failed: %s",
                chat_id,
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
        Prepare Zara for music playback.

        IMPORTANT:

        This method does not call PyTgCalls.play().

        AudioStream.play() will establish the actual
        PyTgCalls connection.

        Before that we verify:

            1. Telethon is available.
            2. Zara is authorized.
            3. Zara is inside the group.
            4. Zara is not banned.
            5. Active VC exists.
        """

        chat_id = int(chat_id)

        self.clear_join_error(
            chat_id
        )

        # Already prepared.
        if chat_id in self.joined_chats:

            # Still verify that an active call exists.
            active = await self.has_active_call(
                chat_id
            )

            if active:
                return True

            # Old state is stale.
            self.joined_chats.discard(
                chat_id
            )

        # ----------------------------------------------------
        # GROUP MEMBERSHIP
        # ----------------------------------------------------

        membership = (
            await self._check_group_membership(
                chat_id
            )
        )

        if membership != "ok":

            if membership == "banned":

                logger.warning(
                    "Zara is banned in group: %s",
                    chat_id,
                )

            elif membership == "not_in_group":

                logger.warning(
                    "Zara is not a member of group: %s",
                    chat_id,
                )

            return False

        # ----------------------------------------------------
        # ACTIVE VOICE CHAT
        # ----------------------------------------------------

        active = await self.has_active_call(
            chat_id
        )

        if not active:

            self._set_join_error(
                chat_id,
                "no_active_call",
            )

            logger.warning(
                "No active VC found for %s.",
                chat_id,
            )

            return False

        # ----------------------------------------------------
        # REGISTER STREAM HANDLER
        # ----------------------------------------------------

        if not self._registered:

            await self.register()

        # ----------------------------------------------------
        # READY
        # ----------------------------------------------------

        self.joined_chats.add(
            chat_id
        )

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

        update_type = type(
            update
        ).__name__

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

                    if isinstance(
                        value,
                        bytes,
                    ):

                        attributes[name] = (
                            f"<bytes:{len(value)}>"
                        )

                    else:

                        text = repr(
                            value
                        )

                        if len(text) > 300:

                            text = (
                                text[:300]
                                + "..."
                            )

                        attributes[name] = text

                except Exception:
                    continue

            logger.info(
                "PyTgCalls update detected: "
                "%s | attrs=%s",
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

            if isinstance(
                value,
                bytes,
            ):

                return value

            if isinstance(
                value,
                bytearray,
            ):

                return bytes(
                    value
                )

            if isinstance(
                value,
                memoryview,
            ):

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

            audio_data = (
                self._extract_audio_bytes(
                    update
                )
            )

            if not audio_data:
                return

            logger.debug(
                "Received VC audio frame: "
                "chat=%s bytes=%s",
                chat_id,
                len(audio_data),
            )

            # STT buffering will be connected here.
            #
            # Do not send individual raw frames
            # directly to Gemini.

        except Exception:

            logger.exception(
                "Failed to process "
                "PyTgCalls stream frame."
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

            if hasattr(
                result,
                "__await__",
            ):

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

            self.last_join_error.pop(
                chat_id,
                None,
            )

    # ========================================================
    # STATUS
    # ========================================================

    def is_joined(
        self,
        chat_id: int,
    ) -> bool:

        return (
            int(chat_id)
            in self.joined_chats
        )

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

    async def cleanup(
        self,
    ) -> None:

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
        self.last_join_error.clear()

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
