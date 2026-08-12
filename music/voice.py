import logging
import re

from ai.intent import (
    MUSIC_PLAY,
    MUSIC_SEARCH,
    MUSIC_PAUSE,
    MUSIC_RESUME,
    MUSIC_SKIP,
    MUSIC_STOP,
    MUSIC_QUEUE,
    MUSIC_REMOVE,
    MUSIC_VIDEO,
    detect_rule_based,
    extract_music_query,
)

from config import (
    OWNER_ID,
    MUSIC_MAX_QUEUE,
)

from database.groups import (
    get_group_setting,
    set_group_setting,
    get_or_create_group,
)

from music.queue import Track

logger = logging.getLogger(__name__)


MODE_KEY = "music_request_mode"
MODE_ALL = "all"
MODE_ADMIN = "admin"


def _is_admin_status(
    status: str,
) -> bool:

    return status in {
        "administrator",
        "creator",
        "owner",
    }


class VoiceMusicController:
    """
    Converts VC speech into music commands.
    """

    def __init__(
        self,
        *,
        bot,
        user_client,
        player,
        downloader,
        searcher,
        controls,
    ):
        self.bot = bot
        self.user_client = user_client
        self.player = player
        self.downloader = downloader
        self.searcher = searcher
        self.controls = controls

    # ========================================================
    # MODE
    # ========================================================

    async def mode(
        self,
        chat_id: int,
    ) -> str:

        value = await get_group_setting(
            chat_id,
            MODE_KEY,
            MODE_ADMIN,
        )

        value = str(
            value or MODE_ADMIN
        ).lower()

        if value not in {
            MODE_ALL,
            MODE_ADMIN,
        }:
            return MODE_ADMIN

        return value

    async def set_mode(
        self,
        chat_id: int,
        value: str,
    ) -> bool:

        value = (
            MODE_ALL
            if value == MODE_ALL
            else MODE_ADMIN
        )

        await get_or_create_group(
            chat_id
        )

        return await set_group_setting(
            chat_id,
            MODE_KEY,
            value,
        )

    # ========================================================
    # PERMISSIONS
    # ========================================================

    async def _is_group_admin(
        self,
        chat_id: int,
        user_id: int,
    ) -> bool:

        if user_id == OWNER_ID:
            return True

        try:
            member = await self.bot.get_chat_member(
                chat_id,
                user_id,
            )

            return _is_admin_status(
                str(
                    member.status
                ).lower()
            )

        except Exception:
            return False

    async def can_request(
        self,
        chat_id: int,
        user_id: int,
    ) -> bool:

        if user_id == OWNER_ID:
            return True

        if (
            await self.mode(chat_id)
            == MODE_ALL
        ):
            return True

        return await self._is_group_admin(
            chat_id,
            user_id,
        )

    async def can_control(
        self,
        chat_id: int,
        user_id: int,
    ) -> bool:

        if user_id == OWNER_ID:
            return True

        if await self._is_group_admin(
            chat_id,
            user_id,
        ):
            return True

        current = self.player.current(
            chat_id
        )

        return bool(
            current
            and current.requested_by
            == user_id
        )

    # ========================================================
    # HELPERS
    # ========================================================

    async def _name(
        self,
        user_id: int,
    ) -> str:

        try:
            entity = await self.user_client.get_entity(
                user_id
            )

            first = (
                getattr(
                    entity,
                    "first_name",
                    None,
                )
                or "User"
            )

            last = (
                getattr(
                    entity,
                    "last_name",
                    None,
                )
                or ""
            )

            return (
                f"{first} {last}"
            ).strip()

        except Exception:
            return f"User {user_id}"

    async def _announce(
        self,
        chat_id: int,
        text: str,
    ) -> None:

        try:
            await self.bot.send_message(
                chat_id,
                text,
            )

        except Exception:
            logger.exception(
                "Failed to announce music state in %s",
                chat_id,
            )

    # ========================================================
    # REQUEST SONG
    # ========================================================

    async def request_song(
        self,
        chat_id: int,
        user_id: int,
        transcript: str,
        *,
        video: bool = False,
    ) -> bool:

        if not await self.can_request(
            chat_id,
            user_id,
        ):

            await self._announce(
                chat_id,
                "⛔ Is group me sirf admin/owner song request kar sakta hai.",
            )

            return False

        query = extract_music_query(
            transcript
        )

        query = re.sub(
            r"^zara[,:\s-]*",
            "",
            query,
            flags=re.I,
        ).strip()

        query = re.sub(
            r"\b(?:video|vidio)\s+(?:chalao|bajao|play|dikhao)\b",
            "",
            query,
            flags=re.I,
        ).strip()

        if not query:

            await self._announce(
                chat_id,
                "🎵 Song ka naam bolo.",
            )

            return False

        if (
            self.player.queue_size(
                chat_id
            )
            >= int(MUSIC_MAX_QUEUE)
        ):

            await self._announce(
                chat_id,
                "⚠️ Music queue full hai.",
            )

            return False

        logger.info(
            "VC music request: chat=%s user=%s query=%s video=%s",
            chat_id,
            user_id,
            query,
            video,
        )

        # ----------------------------------------------------
        # SEARCH
        # ----------------------------------------------------

        try:
            result = await self.searcher.first(
                query
            )
        except Exception:
            logger.exception(
                "Music search failed: %s",
                query,
            )

            await self._announce(
                chat_id,
                "❌ Song search me error aa gaya.",
            )

            return False

        if not result:

            await self._announce(
                chat_id,
                f"❌ <b>{query}</b> nahi mila.",
            )

            return False

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        try:
            path = await self.downloader.download(
                result,
                video=video,
            )
        except Exception:
            logger.exception(
                "Music download failed: %s",
                result.title,
            )

            await self._announce(
                chat_id,
                "❌ Song download nahi ho paya.",
            )

            return False

        if not path:

            await self._announce(
                chat_id,
                "❌ Song/media download nahi ho paya.",
            )

            return False

        logger.info(
            "Music downloaded: %s -> %s",
            result.title,
            path,
        )

        # ----------------------------------------------------
        # TRACK
        # ----------------------------------------------------

        name = await self._name(
            user_id
        )

        track = Track(
            title=result.title,
            url=result.url,
            audio_path=path,
            duration=result.duration,
            requested_by=user_id,
            requested_by_name=name,
            thumbnail=result.thumbnail,
            source="youtube",
            media_type=(
                "video"
                if video
                else "audio"
            ),
            metadata={
                "query": query,
                "video_id": result.video_id,
            },
        )

        was_playing = self.player.is_playing(
            chat_id
        )

        # ----------------------------------------------------
        # ADD + PLAY
        # ----------------------------------------------------

        position = await self.player.add(
            chat_id,
            track,
            play_now=not was_playing,
        )

        if not was_playing:

            current = self.player.current(
                chat_id
            )

            if (
                current is None
                or current.title
                != track.title
                or not self.player.is_playing(
                    chat_id
                )
            ):

                await self._announce(
                    chat_id,
                    "❌ Song download ho gaya, lekin VC me playback start nahi hua.",
                )

                logger.error(
                    "Playback failed after queue add: chat=%s title=%s",
                    chat_id,
                    track.title,
                )

                return False

            await self._announce(
                chat_id,
                f"🎵 <b>{name}</b> ka request play ho raha hai:\n"
                f"<b>{result.title}</b>",
            )

        else:

            queue_position = (
                self.player.queue_size(
                    chat_id
                )
            )

            await self._announce(
                chat_id,
                f"🎵 <b>{name}</b> ne <b>{result.title}</b> request kiya.\n"
                f"⏭️ Queue position: <b>{queue_position}</b>",
            )

        return True

    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
        chat_id: int,
        clear_queue: bool = True,
    ) -> bool:
        """
        Stop music and optionally clear queue.

        This method is required by telegram/events.py /end.
        """

        try:

            ok = await self.player.stop(
                chat_id,
                clear=clear_queue,
            )

            logger.info(
                "Voice music controller stopped: %s",
                chat_id,
            )

            return bool(ok)

        except Exception:
            logger.exception(
                "Voice music controller stop failed: %s",
                chat_id,
            )
            return False

    # ========================================================
    # HANDLE TRANSCRIPT
    # ========================================================

    async def handle(
        self,
        chat_id: int,
        user_id: int,
        transcript: str,
    ) -> bool:

        text = str(
            transcript or ""
        ).strip()

        if not text:
            return False

        logger.info(
            "VC command: chat=%s user=%s text=%s",
            chat_id,
            user_id,
            text,
        )

        try:
            result = detect_rule_based(
                text
            )

            intent = result.intent

        except Exception:
            logger.exception(
                "Music intent detection failed."
            )
            return False

        video = bool(
            re.search(
                r"\b(video|vidio)\b",
                text,
                re.I,
            )
        )

        if (
            video
            and intent
            in {
                MUSIC_PLAY,
                MUSIC_SEARCH,
            }
        ):
            intent = MUSIC_VIDEO

        # ----------------------------------------------------
        # PLAY / SEARCH / VIDEO
        # ----------------------------------------------------

        if intent in {
            MUSIC_PLAY,
            MUSIC_SEARCH,
            MUSIC_VIDEO,
        }:

            return await self.request_song(
                chat_id,
                user_id,
                text,
                video=video,
            )

        # ----------------------------------------------------
        # QUEUE
        # ----------------------------------------------------

        if intent == MUSIC_QUEUE:

            current = self.player.current(
                chat_id
            )

            queue = self.player.get_queue(
                chat_id
            )

            lines = [
                "🎵 <b>Zara Music Queue</b>"
            ]

            if current:

                lines.append(
                    f"▶️ Now: <b>{current.title}</b>"
                    f" — {current.requested_by_name or 'User'}"
                )

            for index, track in enumerate(
                queue,
                1,
            ):

                lines.append(
                    f"{index}. <b>{track.title}</b>"
                    f" — {track.requested_by_name or 'User'}"
                )

            if not current and not queue:
                lines.append(
                    "📭 Queue empty hai."
                )

            await self._announce(
                chat_id,
                "\n".join(lines),
            )

            return True

        # ----------------------------------------------------
        # CONTROLS
        # ----------------------------------------------------

        if intent in {
            MUSIC_PAUSE,
            MUSIC_RESUME,
            MUSIC_SKIP,
            MUSIC_STOP,
            MUSIC_REMOVE,
        }:

            if not await self.can_control(
                chat_id,
                user_id,
            ):

                await self._announce(
                    chat_id,
                    "⛔ Sirf current song requester ya group admin/owner control kar sakta hai.",
                )

                return True

            if intent == MUSIC_PAUSE:

                ok = await self.controls.pause(
                    chat_id
                )

                await self._announce(
                    chat_id,
                    "⏸️ Music paused."
                    if ok
                    else "❌ Pause nahi hua.",
                )

            elif intent == MUSIC_RESUME:

                ok = await self.controls.resume(
                    chat_id
                )

                await self._announce(
                    chat_id,
                    "▶️ Music resumed."
                    if ok
                    else "❌ Resume nahi hua.",
                )

            elif intent == MUSIC_SKIP:

                old = self.player.current(
                    chat_id
                )

                ok = await self.controls.skip(
                    chat_id
                )

                if ok:

                    current = self.player.current(
                        chat_id
                    )

                    if current:

                        await self._announce(
                            chat_id,
                            f"⏭️ <b>{old.title if old else 'Current song'}</b> skipped.\n"
                            f"▶️ Next: <b>{current.title}</b>",
                        )

                    else:

                        await self._announce(
                            chat_id,
                            "⏭️ Song skipped. Queue empty hai.",
                        )

                else:

                    await self._announce(
                        chat_id,
                        "📭 Queue empty hai.",
                    )

            elif intent == MUSIC_STOP:

                await self.stop(
                    chat_id,
                    clear_queue=True,
                )

                await self._announce(
                    chat_id,
                    "⏹️ Music stopped aur queue clear kar di.",
                )

            elif intent == MUSIC_REMOVE:

                queue = self.player.get_queue(
                    chat_id
                )

                if not queue:

                    await self._announce(
                        chat_id,
                        "📭 Queue empty hai.",
                    )

                else:

                    from music.queue import remove_from_queue

                    item = remove_from_queue(
                        chat_id,
                        0,
                    )

                    await self._announce(
                        chat_id,
                        (
                            f"🗑️ Removed: <b>{item.title}</b>"
                            if item
                            else "❌ Song remove nahi hua."
                        ),
                    )

            return True

        return False


__all__ = [
    "VoiceMusicController",
    "MODE_ALL",
    "MODE_ADMIN",
    "MODE_KEY",
]
