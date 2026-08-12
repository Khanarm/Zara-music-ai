# music/player.py

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from audio.stream import AudioStream
from music.queue import (
    Track, add_to_queue, clear_queue, get_queue,
    is_queue_empty, pop_next, queue_size,
)

logger = logging.getLogger(__name__)


@dataclass
class PlayerState:
    chat_id: int
    current: Optional[Track] = None
    playing: bool = False
    paused: bool = False
    loop: bool = False


class MusicPlayer:
    """FIFO Telegram VC player with requester-aware tracks."""

    def __init__(self, audio_stream: AudioStream):
        self.audio_stream = audio_stream
        self.players: dict[int, PlayerState] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _player(self, chat_id: int) -> PlayerState:
        return self.players.setdefault(int(chat_id), PlayerState(int(chat_id)))

    def _lock(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(int(chat_id), asyncio.Lock())

    async def add(self, chat_id: int, track: Track, play_now: bool = False) -> int:
        if not isinstance(track, Track):
            raise TypeError("track must be Track")
        position = add_to_queue(chat_id, track)
        player = self._player(chat_id)
        if play_now or (player.current is None and not player.playing):
            await self.play_next(chat_id)
        return position

    async def play_current(self, chat_id: int) -> bool:
        player = self._player(chat_id)
        track = player.current
        if track is None or not track.audio_path:
            return False
        ok = await self.audio_stream.play(
            int(chat_id),
            track.audio_path,
            video=(getattr(track, "media_type", "audio") == "video"),
        )
        player.playing = bool(ok)
        player.paused = False
        return bool(ok)

    async def play_next(self, chat_id: int) -> bool:
        chat_id = int(chat_id)
        async with self._lock(chat_id):
            player = self._player(chat_id)
            if player.loop and player.current is not None:
                return await self.play_current(chat_id)
            player.playing = False
            player.paused = False
            while True:
                track = pop_next(chat_id)
                if track is None:
                    player.current = None
                    return False
                player.current = track
                ok = await self.play_current(chat_id)
                if ok:
                    return True
                player.current = None
                if is_queue_empty(chat_id):
                    return False

    async def on_stream_ended(self, chat_id: int) -> bool:
        """Called by PyTgCalls when the current media reaches EOF."""
        player = self._player(chat_id)
        player.playing = False
        player.paused = False
        if player.loop and player.current is not None:
            return await self.play_current(chat_id)
        player.current = None
        try:
            self.audio_stream.current_streams.pop(int(chat_id), None)
            self.audio_stream.current_media.pop(int(chat_id), None)
        except Exception:
            pass
        return await self.play_next(chat_id)

    async def skip(self, chat_id: int) -> bool:
        player = self._player(chat_id)
        player.loop = False
        return await self.play_next(chat_id)

    async def stop(self, chat_id: int, clear: bool = False) -> bool:
        chat_id = int(chat_id)
        async with self._lock(chat_id):
            ok = await self.audio_stream.stop(chat_id)
            player = self._player(chat_id)
            player.playing = False
            player.paused = False
            player.current = None
            player.loop = False
            if clear:
                clear_queue(chat_id)
            return ok

    async def pause(self, chat_id: int) -> bool:
        ok = await self.audio_stream.pause(int(chat_id))
        if ok:
            p = self._player(chat_id)
            p.paused = True
            p.playing = False
        return bool(ok)

    async def resume(self, chat_id: int) -> bool:
        ok = await self.audio_stream.resume(int(chat_id))
        if ok:
            p = self._player(chat_id)
            p.paused = False
            p.playing = True
        return bool(ok)

    def set_loop(self, chat_id: int, enabled: bool) -> bool:
        self._player(chat_id).loop = bool(enabled)
        return bool(enabled)

    def toggle_loop(self, chat_id: int) -> bool:
        p = self._player(chat_id)
        p.loop = not p.loop
        return p.loop

    def current(self, chat_id: int) -> Optional[Track]:
        p = self.players.get(int(chat_id))
        return p.current if p else None

    def get_queue(self, chat_id: int) -> list[Track]:
        return get_queue(int(chat_id))

    def queue_size(self, chat_id: int) -> int:
        return queue_size(int(chat_id))

    def is_playing(self, chat_id: int) -> bool:
        p = self.players.get(int(chat_id))
        return bool(p and p.playing and not p.paused)

    def is_paused(self, chat_id: int) -> bool:
        p = self.players.get(int(chat_id))
        return bool(p and p.paused)

    def get_status(self, chat_id: int) -> dict[str, Any]:
        p = self.players.get(int(chat_id))
        return {
            "chat_id": int(chat_id),
            "playing": bool(p and p.playing),
            "paused": bool(p and p.paused),
            "loop": bool(p and p.loop),
            "current": p.current.to_dict() if p and p.current else None,
            "queue_size": queue_size(int(chat_id)),
        }

    async def cleanup_chat(self, chat_id: int) -> None:
        await self.audio_stream.stop(int(chat_id))
        clear_queue(int(chat_id))
        self.players.pop(int(chat_id), None)
        self._locks.pop(int(chat_id), None)

    async def cleanup(self) -> None:
        for chat_id in list(self.players):
            try:
                await self.cleanup_chat(chat_id)
            except Exception:
                logger.exception("Music cleanup failed for %s", chat_id)


_player: Optional[MusicPlayer] = None


def get_player(audio_stream: AudioStream) -> MusicPlayer:
    global _player
    if _player is None:
        _player = MusicPlayer(audio_stream)
    return _player


def reset_player() -> None:
    global _player
    _player = None


__all__ = ["Track", "PlayerState", "MusicPlayer", "get_player", "reset_player"]
