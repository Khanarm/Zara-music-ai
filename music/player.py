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

    Handles:
    - Queue
    - Current track
    - Playback
    - Skip
    - Pause/resume
    - Loop
    - Playback failures
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

        should_start = (
            play_now
            or (
                player.current is None
                and not player.playing
                and not player.paused
            )
        )

        logger.info(
            "Track added chat=%s title=%s "
            "position=%s play_now=%s",
            chat_id,
            track.title,
            position,
            play_now,
        )

        if should_start:

            started = await self.play_next(
                chat_id
            )

            if not started:

                logger.error(
                    "Track could not start "
                    "after being added: %s",
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
                "play_current called with "
                "no current track: %s",
                chat_id,
            )

            return False

        path = getattr(
            track,
            "audio_path",
            None,
        )

        if not path:

            logger.error(
                "Track has no audio_path: %s",
                track.title,
            )

            return False

        logger.info(
            "Playing track chat=%s "
            "title=%s path=%s",
            chat_id,
            track.title,
            path,
        )

        video = (
            getattr(
                track,
                "media_type",
                "audio",
            )
            == "video"
        )

        ok = await self.audio_stream.play(
            chat_id,
            path,
            video=video,
        )

        if ok:

            player.playing = True
            player.paused = False

            logger.info(
                "Track playback confirmed "
                "chat=%s title=%s",
                chat_id,
                track.title,
            )

            return True

        player.playing = False
        player.paused = False

        logger.error(
            "Track playback failed "
            "chat=%s title=%s path=%s",
            chat_id,
            track.title,
            path,
        )

        return False

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

            # ------------------------------------------------
            # Loop current track
            # ------------------------------------------------

            if (
                player.loop
                and player.current is not None
            ):

                logger.info(
                    "Looping current track "
                    "in %s",
                    chat_id,
                )

                return await self.play_current(
                    chat_id
                )

            player.playing = False
            player.paused = False

            # ------------------------------------------------
            # Get next playable track
            # ------------------------------------------------

            while True:

                track = pop_next(
                    chat_id
                )

                if track is None:

                    player.current = None
                    player.playing = False
                    player.paused = False

                    logger.info(
                        "Queue empty for %s",
                        chat_id,
                    )

                    return False

                player.current = track

                logger.info(
                    "Trying next track "
                    "chat=%s title=%s path=%s",
                    chat_id,
                    track.title,
                    getattr(
                        track,
                        "audio_path",
                        None,
                    ),
                )

                ok = await self.play_current(
                    chat_id
                )

                if ok:
                    return True

                # Playback failed.
                # Do not leave a broken current track
                # blocking the queue.

                logger.error(
                    "Skipping unplayable track "
                    "chat=%s title=%s",
                    chat_id,
                    track.title,
                )

                player.current = None
                player.playing = False
                player.paused = False

                if is_queue_empty(
                    chat_id
                ):

                    logger.error(
                        "No playable tracks remain "
                        "in queue %s",
                        chat_id,
                    )

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

        if (
            player.loop
            and player.current is not None
        ):

            return await self.play_current(
                chat_id
            )

        logger.info(
            "Stream ended chat=%s "
            "track=%s",
            chat_id,
            (
                player.current.title
                if player.current
                else None
            ),
        )

        player.current = None

        try:

            self.audio_stream.current_streams.pop(
                chat_id,
                None,
            )

            self.audio_stream.current_media.pop(
                chat_id,
                None,
            )

        except Exception:
            pass

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

        chat_id = int(chat_id)

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
                "Music stopped chat=%s "
                "clear=%s",
                chat_id,
                clear,
            )

            return ok

    # ========================================================
    # PAUSE
    # ========================================================

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        ok = await self.audio_stream.pause(
            chat_id
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

        chat_id = int(chat_id)

        ok = await self.audio_stream.resume(
            chat_id
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

        player = self._player(
            chat_id
        )

        player.loop = bool(
            enabled
        )

        return player.loop

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
    # CURRENT
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

    # ========================================================
    # QUEUE
    # ========================================================

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

    # ========================================================
    # STATE
    # ========================================================

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

    # ========================================================
    # STATUS
    # ========================================================

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
    # CLEANUP CHAT
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

    # ========================================================
    # CLEANUP
    # ========================================================

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
                    "Music cleanup failed "
                    "for %s",
                    chat_id,
                )


# ============================================================
# SINGLETON
# ============================================================

_player: Optional[
    MusicPlayer
] = None


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
