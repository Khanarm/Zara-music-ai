import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional

from audio.stream import AudioStream
from music.queue import (
    Track,
    add_to_queue,
    clear_queue,
    get_queue,
    is_queue_empty,
    pop_next,
    queue_size,
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
    """
    FIFO Telegram VC music player.
    """

    def __init__(
        self,
        audio_stream: AudioStream,
    ):
        self.audio_stream = audio_stream

        self.players: dict[
            int,
            PlayerState,
        ] = {}

        self._locks: dict[
            int,
            asyncio.Lock,
        ] = {}

    # ========================================================
    # INTERNAL
    # ========================================================

    def _player(
        self,
        chat_id: int,
    ) -> PlayerState:

        chat_id = int(chat_id)

        return self.players.setdefault(
            chat_id,
            PlayerState(chat_id),
        )

    def _lock(
        self,
        chat_id: int,
    ) -> asyncio.Lock:

        chat_id = int(chat_id)

        return self._locks.setdefault(
            chat_id,
            asyncio.Lock(),
        )

    # ========================================================
    # ADD
    # ========================================================

    async def add(
        self,
        chat_id: int,
        track: Track,
        play_now: bool = False,
    ) -> int:

        chat_id = int(chat_id)

        if not isinstance(
            track,
            Track,
        ):
            raise TypeError(
                "track must be Track"
            )

        position = add_to_queue(
            chat_id,
            track,
        )

        player = self._player(
            chat_id
        )

        should_play = (
            play_now
            or (
                player.current is None
                and not player.playing
            )
        )

        logger.info(
            "Track added: chat=%s title=%s play_now=%s",
            chat_id,
            track.title,
            should_play,
        )

        if should_play:
            started = await self.play_next(
                chat_id
            )

            if not started:
                logger.error(
                    "Track was queued but playback failed: chat=%s title=%s",
                    chat_id,
                    track.title,
                )

        return position

    # ========================================================
    # PLAY CURRENT
    # ========================================================

    async def play_current(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        player = self._player(
            chat_id
        )

        track = player.current

        if track is None:
            logger.warning(
                "play_current called with no current track: %s",
                chat_id,
            )
            return False

        if not track.audio_path:
            logger.error(
                "Track has no audio path: %s",
                track.title,
            )
            return False

        logger.info(
            "Playing current track: chat=%s title=%s path=%s",
            chat_id,
            track.title,
            track.audio_path,
        )

        ok = await self.audio_stream.play(
            chat_id,
            track.audio_path,
            video=(
                getattr(
                    track,
                    "media_type",
                    "audio",
                )
                == "video"
            ),
        )

        player.playing = bool(ok)
        player.paused = False

        if ok:
            logger.info(
                "Music playback active: chat=%s title=%s",
                chat_id,
                track.title,
            )
        else:
            logger.error(
                "Music playback failed: chat=%s title=%s",
                chat_id,
                track.title,
            )

        return bool(ok)

    # ========================================================
    # PLAY NEXT
    # ========================================================

    async def play_next(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        async with self._lock(
            chat_id
        ):

            player = self._player(
                chat_id
            )

            if (
                player.loop
                and player.current is not None
            ):
                return await self.play_current(
                    chat_id
                )

            player.playing = False
            player.paused = False

            while True:

                track = pop_next(
                    chat_id
                )

                if track is None:
                    player.current = None

                    logger.info(
                        "No more tracks in queue: %s",
                        chat_id,
                    )

                    return False

                player.current = track

                logger.info(
                    "Starting next track: chat=%s title=%s",
                    chat_id,
                    track.title,
                )

                ok = await self.play_current(
                    chat_id
                )

                if ok:
                    return True

                logger.error(
                    "Skipping failed track: %s",
                    track.title,
                )

                player.current = None

                if is_queue_empty(
                    chat_id
                ):
                    return False

    # ========================================================
    # STREAM ENDED
    # ========================================================

    async def on_stream_ended(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        player = self._player(
            chat_id
        )

        player.playing = False
        player.paused = False

        logger.info(
            "Stream ended: %s",
            chat_id,
        )

        if (
            player.loop
            and player.current is not None
        ):
            return await self.play_current(
                chat_id
            )

        player.current = None

        self.audio_stream.current_streams.pop(
            chat_id,
            None,
        )

        self.audio_stream.current_media.pop(
            chat_id,
            None,
        )

        return await self.play_next(
            chat_id
        )

    # ========================================================
    # SKIP
    # ========================================================

    async def skip(
        self,
        chat_id: int,
    ) -> bool:

        player = self._player(
            chat_id
        )

        player.loop = False

        return await self.play_next(
            chat_id
        )

    # ========================================================
    # STOP
    # ========================================================

    async def stop(
        self,
        chat_id: int,
        clear: bool = False,
    ) -> bool:

        chat_id = int(chat_id)

        async with self._lock(
            chat_id
        ):

            ok = await self.audio_stream.stop(
                chat_id
            )

            player = self._player(
                chat_id
            )

            player.playing = False
            player.paused = False
            player.current = None
            player.loop = False

            if clear:
                clear_queue(
                    chat_id
                )

            logger.info(
                "Music player stopped: %s",
                chat_id,
            )

            return bool(ok)

    # ========================================================
    # PAUSE
    # ========================================================

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        ok = await self.audio_stream.pause(
            int(chat_id)
        )

        if ok:
            player = self._player(
                chat_id
            )

            player.paused = True
            player.playing = False

        return bool(ok)

    # ========================================================
    # RESUME
    # ========================================================

    async def resume(
        self,
        chat_id: int,
    ) -> bool:

        ok = await self.audio_stream.resume(
            int(chat_id)
        )

        if ok:
            player = self._player(
                chat_id
            )

            player.paused = False
            player.playing = True

        return bool(ok)

    # ========================================================
    # LOOP
    # ========================================================

    def set_loop(
        self,
        chat_id: int,
        enabled: bool,
    ) -> bool:

        self._player(
            chat_id
        ).loop = bool(enabled)

        return bool(enabled)

    def toggle_loop(
        self,
        chat_id: int,
    ) -> bool:

        player = self._player(
            chat_id
        )

        player.loop = not player.loop

        return player.loop

    # ========================================================
    # GETTERS
    # ========================================================

    def current(
        self,
        chat_id: int,
    ) -> Optional[Track]:

        player = self.players.get(
            int(chat_id)
        )

        return (
            player.current
            if player
            else None
        )

    def get_queue(
        self,
        chat_id: int,
    ) -> list[Track]:

        return get_queue(
            int(chat_id)
        )

    def queue_size(
        self,
        chat_id: int,
    ) -> int:

        return queue_size(
            int(chat_id)
        )

    def is_playing(
        self,
        chat_id: int,
    ) -> bool:

        player = self.players.get(
            int(chat_id)
        )

        return bool(
            player
            and player.playing
            and not player.paused
        )

    def is_paused(
        self,
        chat_id: int,
    ) -> bool:

        player = self.players.get(
            int(chat_id)
        )

        return bool(
            player
            and player.paused
        )

    def get_status(
        self,
        chat_id: int,
    ) -> dict[str, Any]:

        player = self.players.get(
            int(chat_id)
        )

        return {
            "chat_id": int(chat_id),
            "playing": bool(
                player
                and player.playing
            ),
            "paused": bool(
                player
                and player.paused
            ),
            "loop": bool(
                player
                and player.loop
            ),
            "current": (
                player.current.to_dict()
                if player
                and player.current
                else None
            ),
            "queue_size": queue_size(
                int(chat_id)
            ),
        }

    # ========================================================
    # CLEANUP
    # ========================================================

    async def cleanup_chat(
        self,
        chat_id: int,
    ) -> None:

        chat_id = int(chat_id)

        await self.audio_stream.stop(
            chat_id
        )

        clear_queue(
            chat_id
        )

        self.players.pop(
            chat_id,
            None,
        )

        self._locks.pop(
            chat_id,
            None,
        )

    async def cleanup(self) -> None:

        for chat_id in list(
            self.players
        ):

            try:
                await self.cleanup_chat(
                    chat_id
                )
            except Exception:
                logger.exception(
                    "Music cleanup failed for %s",
                    chat_id,
                )


_player: Optional[MusicPlayer] = None


def get_player(
    audio_stream: AudioStream,
) -> MusicPlayer:

    global _player

    if _player is None:
        _player = MusicPlayer(
            audio_stream
        )

    return _player


def reset_player() -> None:

    global _player

    _player = None


__all__ = [
    "Track",
    "PlayerState",
    "MusicPlayer",
    "get_player",
    "reset_player",
]
