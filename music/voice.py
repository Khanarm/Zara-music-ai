# music/voice.py

import logging
import re
from typing import Optional

from ai.intent import (
    MUSIC_PLAY, MUSIC_SEARCH, MUSIC_PAUSE, MUSIC_RESUME,
    MUSIC_SKIP, MUSIC_STOP, MUSIC_QUEUE, MUSIC_REMOVE,
    MUSIC_VIDEO, detect_rule_based, extract_music_query,
)
from config import OWNER_ID, MUSIC_MAX_QUEUE
from database.groups import get_group_setting, set_group_setting, get_or_create_group
from music.queue import Track

logger = logging.getLogger(__name__)

MODE_KEY = "music_request_mode"
MODE_ALL = "all"
MODE_ADMIN = "admin"


def _is_admin_status(status: str) -> bool:
    return status in {"administrator", "creator", "owner"}


class VoiceMusicController:
    """Turns transcribed VC speech into music operations."""

    def __init__(self, *, bot, user_client, player, downloader, searcher, controls):
        self.bot = bot
        self.user_client = user_client
        self.player = player
        self.downloader = downloader
        self.searcher = searcher
        self.controls = controls

    async def mode(self, chat_id: int) -> str:
        value = await get_group_setting(chat_id, MODE_KEY, MODE_ADMIN)
        value = str(value or MODE_ADMIN).lower()
        return value if value in {MODE_ALL, MODE_ADMIN} else MODE_ADMIN

    async def set_mode(self, chat_id: int, value: str) -> bool:
        value = MODE_ALL if value == MODE_ALL else MODE_ADMIN
        await get_or_create_group(chat_id)
        return await set_group_setting(chat_id, MODE_KEY, value)

    async def _is_group_admin(self, chat_id: int, user_id: int) -> bool:
        if user_id == OWNER_ID:
            return True
        try:
            member = await self.bot.get_chat_member(chat_id, user_id)
            return _is_admin_status(str(member.status).lower())
        except Exception:
            return False

    async def can_request(self, chat_id: int, user_id: int) -> bool:
        if user_id == OWNER_ID:
            return True
        if await self.mode(chat_id) == MODE_ALL:
            return True
        return await self._is_group_admin(chat_id, user_id)

    async def can_control(self, chat_id: int, user_id: int) -> bool:
        if user_id == OWNER_ID:
            return True
        if await self._is_group_admin(chat_id, user_id):
            return True
        current = self.player.current(chat_id)
        return bool(current and current.requested_by == user_id)

    async def _name(self, user_id: int) -> str:
        try:
            entity = await self.user_client.get_entity(user_id)
            first = getattr(entity, "first_name", None) or "User"
            last = getattr(entity, "last_name", None) or ""
            return (f"{first} {last}").strip()
        except Exception:
            return f"User {user_id}"

    async def _announce(self, chat_id: int, text: str) -> None:
        try:
            await self.bot.send_message(chat_id, text)
        except Exception:
            logger.exception("Failed to announce music state in %s", chat_id)

    async def request_song(self, chat_id: int, user_id: int, transcript: str, *, video: bool = False) -> bool:
        if not await self.can_request(chat_id, user_id):
            await self._announce(chat_id, f"⛔ User {user_id} ko song request ki permission nahi hai.")
            return False

        query = extract_music_query(transcript)
        query = re.sub(r"^zara[,:\s-]*", "", query, flags=re.I).strip()
        query = re.sub(r"\b(?:video|vidio)\s+(?:chalao|bajao|play|dikhao)\b", "", query, flags=re.I).strip()
        if not query:
            await self._announce(chat_id, "🎵 Song ka naam bolo.")
            return False

        if self.player.queue_size(chat_id) >= int(MUSIC_MAX_QUEUE):
            await self._announce(chat_id, "⚠️ Music queue full hai.")
            return False

        result = await self.searcher.first(query)
        if not result:
            await self._announce(chat_id, f"❌ {query} nahi mila.")
            return False

        path = await self.downloader.download(result, video=video)
        if not path:
            await self._announce(chat_id, "❌ Song/media download nahi ho paya.")
            return False

        name = await self._name(user_id)
        track = Track(
            title=result.title,
            url=result.url,
            audio_path=path,
            duration=result.duration,
            requested_by=user_id,
            requested_by_name=name,
            thumbnail=result.thumbnail,
            source="youtube",
            media_type="video" if video else "audio",
            metadata={"query": query, "video_id": result.video_id},
        )

        was_playing = self.player.is_playing(chat_id)
        position = await self.player.add(chat_id, track, play_now=not was_playing)

        if was_playing:
            queue_position = self.player.queue_size(chat_id)
            await self._announce(
                chat_id,
                f"🎵 <b>{name}</b> ne <b>{result.title}</b> request kiya.\n"
                f"⏭️ Queue position: <b>{queue_position}</b>",
            )
        else:
            await self._announce(
                chat_id,
                f"🎵 <b>{name}</b> ka request play ho raha hai:\n<b>{result.title}</b>",
            )

        next_track = self.player.get_queue(chat_id)[0] if self.player.get_queue(chat_id) else None
        if next_track:
            await self._announce(
                chat_id,
                f"⏭️ Next: <b>{next_track.requested_by_name or 'User'}</b> — <b>{next_track.title}</b>",
            )
        return True

    async def handle(self, chat_id: int, user_id: int, transcript: str) -> bool:
        text = str(transcript or "").strip()
        if not text:
            return False
        result = detect_rule_based(text)
        intent = result.intent

        # Explicit video request gets normal play intent plus video mode.
        video = bool(re.search(r"\b(video|vidio)\b", text, re.I))
        if video and intent in {MUSIC_PLAY, MUSIC_SEARCH}:
            intent = MUSIC_VIDEO

        if intent in {MUSIC_PLAY, MUSIC_SEARCH, MUSIC_VIDEO}:
            return await self.request_song(chat_id, user_id, text, video=video)

        if intent in {MUSIC_PAUSE, MUSIC_RESUME, MUSIC_SKIP, MUSIC_STOP, MUSIC_QUEUE, MUSIC_REMOVE}:
            if intent in {MUSIC_QUEUE}:
                q = self.player.get_queue(chat_id)
                current = self.player.current(chat_id)
                lines = ["🎵 <b>Zara Music Queue</b>"]
                if current:
                    lines.append(f"▶️ Now: <b>{current.title}</b> — {current.requested_by_name or 'User'}")
                for i, track in enumerate(q, 1):
                    lines.append(f"{i}. <b>{track.title}</b> — {track.requested_by_name or 'User'}")
                await self._announce(chat_id, "\n".join(lines))
                return True

            if not await self.can_control(chat_id, user_id):
                await self._announce(chat_id, "⛔ Sirf current song requester ya group admin/owner control kar sakta hai.")
                return True

            if intent == MUSIC_PAUSE:
                ok = await self.controls.pause(chat_id)
                await self._announce(chat_id, "⏸️ Music paused." if ok else "❌ Pause nahi hua.")
            elif intent == MUSIC_RESUME:
                ok = await self.controls.resume(chat_id)
                await self._announce(chat_id, "▶️ Music resumed." if ok else "❌ Resume nahi hua.")
            elif intent == MUSIC_SKIP:
                old = self.player.current(chat_id)
                ok = await self.controls.skip(chat_id)
                if ok:
                    current = self.player.current(chat_id)
                    await self._announce(chat_id, f"⏭️ <b>{old.title if old else 'Current song'}</b> skipped.\n▶️ Next: <b>{current.title}</b>" if current else "⏭️ Song skipped. Queue empty hai.")
                else:
                    await self._announce(chat_id, "📭 Queue empty hai.")
            elif intent == MUSIC_STOP:
                await self.controls.stop(chat_id, clear_queue=True)
                await self._announce(chat_id, "⏹️ Music stopped aur queue clear kar di.")
            elif intent == MUSIC_REMOVE:
                removed = self.player.get_queue(chat_id)
                if removed:
                    from music.queue import remove_from_queue
                    item = remove_from_queue(chat_id, 0)
                    await self._announce(chat_id, f"🗑️ Removed: <b>{item.title}</b>" if item else "❌ Queue empty hai.")
                else:
                    await self._announce(chat_id, "📭 Queue empty hai.")
            return True

        return False


__all__ = ["VoiceMusicController", "MODE_ALL", "MODE_ADMIN", "MODE_KEY"]
