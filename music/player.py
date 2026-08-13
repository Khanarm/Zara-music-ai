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
    remove_user_track,
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

        self._watchers: dict[
            int,
            asyncio.Task,
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

        return self._locks.setdefault(
            int(chat_id),
            asyncio.Lock(),
        )

    # ========================================================
    # CLEAN FILE
    # ========================================================

    async def _delete_track_file(
        self,
        track: Optional[Track],
    ) -> None:

        if track is None:
            return

        path = getattr(
            track,
            "audio_path",
            None,
        )

        if not path:
            return

        try:

            from telegram.client import (
                music_downloader,
            )

            if music_downloader is not None:

                await music_downloader.delete(
                    path
                )

                logger.info(
                    "Deleted media: %s",
                    path,
                )

                return

        except Exception:

            logger.debug(
                "Downloader cleanup failed.",
                exc_info=True,
            )

        try:

            from pathlib import Path

            Path(path).unlink(
                missing_ok=True
            )

            logger.info(
                "Deleted media directly: %s",
                path,
            )

        except Exception:

            logger.warning(
                "Could not delete media: %s",
                path,
                exc_info=True,
            )

    # ========================================================
    # WATCHER
    # ========================================================

    def _cancel_watcher(
        self,
        chat_id: int,
    ) -> None:

        task = self._watchers.pop(
            int(chat_id),
            None,
        )

        if task is not None:

            if not task.done():
                task.cancel()

    def _start_watcher(
        self,
        chat_id: int,
        track: Track,
    ) -> None:

        self._cancel_watcher(
            chat_id
        )

        duration = getattr(
            track,
            "duration",
            None,
        )

        try:
            duration = float(
                duration or 0
            )

        except Exception:
            duration = 0

        if duration <= 0:

            logger.warning(
                "Invalid duration for watcher: %s",
                track.title,
            )

            return

        self._watchers[
            int(chat_id)
        ] = asyncio.create_task(
            self._watch_stream(
                int(chat_id),
                track,
                duration,
            )
        )

    async def _watch_stream(
        self,
        chat_id: int,
        track: Track,
        duration: float,
    ) -> None:

        try:

            await asyncio.sleep(
                max(
                    0.75,
                    duration + 0.5,
                )
            )

            player = self._player(
                chat_id
            )

            if player.current is not track:
                return

            if not player.playing:
                return

            logger.info(
                "Track finished by duration: "
                "chat=%s title=%s",
                chat_id,
                track.title,
            )

            await self.on_stream_ended(
                chat_id
            )

        except asyncio.CancelledError:
            return

        except Exception:

            logger.exception(
                "Playback watcher failed: %s",
                chat_id,
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

        if should_start:

            started = await self.play_next(
                chat_id
            )

            if not started:

                logger.error(
                    "Failed to start track: %s",
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

            logger.error(
                "PLAY CURRENT FAILED: no current track."
            )

            return False

        path = getattr(
            track,
            "audio_path",
            None,
        )

        if not path:

            logger.error(
                "PLAY CURRENT FAILED: no media path: %s",
                track.title,
            )

            return False

        media_type = getattr(
            track,
            "media_type",
            "audio",
        )

        video = (
            str(media_type).lower()
            == "video"
        )

        logger.info(
            "Starting current track: "
            "chat=%s title=%s media=%s path=%s",
            chat_id,
            track.title,
            media_type,
            path,
        )

        ok = await self.audio_stream.play(
            chat_id,
            path,
            video=video,
        )

        if not ok:

            player.playing = False
            player.paused = False

            logger.error(
                "AudioStream playback failed: %s",
                track.title,
            )

            return False

        player.playing = True
        player.paused = False

        self._start_watcher(
            chat_id,
            track,
        )

        logger.info(
            "PLAYING SUCCESS chat=%s title=%s requester=%s",
            chat_id,
            track.title,
            track.requested_by,
        )

        return True

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
            # LOOP
            # ------------------------------------------------

            if (
                player.loop
                and player.current is not None
            ):

                return await self.play_current(
                    chat_id
                )

            old_track = player.current

            player.playing = False
            player.paused = False

            self._cancel_watcher(
                chat_id
            )

            # ------------------------------------------------
            # Remove old media
            # ------------------------------------------------

            if old_track is not None:

                await self._delete_track_file(
                    old_track
                )

            # ------------------------------------------------
            # Find next valid track
            # ------------------------------------------------

            while True:

                track = pop_next(
                    chat_id
                )

                if track is None:

                    player.current = None
                    player.playing = False
                    player.paused = False

                    return False

                player.current = track

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
                player.playing = False
                player.paused = False

                await self._delete_track_file(
                    track
                )

                if is_queue_empty(
                    chat_id
                ):
                    return False

    # ========================================================
    # STREAM END
    # ========================================================

    async def on_stream_ended(
        self,
        chat_id: int,
    ) -> bool:

        chat_id = int(chat_id)

        self._cancel_watcher(
            chat_id
        )

        player = self._player(
            chat_id
        )

        finished = player.current

        player.playing = False
        player.paused = False

        # ----------------------------------------------------
        # LOOP
        # ----------------------------------------------------

        if (
            player.loop
            and finished is not None
        ):

            return await self.play_current(
                chat_id
            )

        # ----------------------------------------------------
        # Clear current media state
        # ----------------------------------------------------

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

            self.audio_stream.connected_chats.discard(
                chat_id
            )

        except Exception:
            pass

        # ----------------------------------------------------
        # Delete finished file
        # ----------------------------------------------------

        await self._delete_track_file(
            finished
        )

        # ----------------------------------------------------
        # Continue queue
        # ----------------------------------------------------

        return await self.play_next(
            chat_id
        )

    # ========================================================
    # SKIP FOR USER
    # ========================================================

    async def skip_for_user(
        self,
        chat_id: int,
        user_id: int,
        is_admin: bool = False,
    ) -> tuple[str, Optional[Track]]:

        chat_id = int(chat_id)
        user_id = int(user_id)

        player = self._player(
            chat_id
        )

        # ----------------------------------------------------
        # ADMIN
        # ----------------------------------------------------

        if is_admin:

            if player.current is None:
                return (
                    "empty",
                    None,
                )

            current = player.current

            self._cancel_watcher(
                chat_id
            )

            result = await self.play_next(
                chat_id
            )

            return (
                "current" if result else "stopped",
                current,
            )

        # ----------------------------------------------------
        # OWN CURRENT SONG
        # ----------------------------------------------------

        if (
            player.current is not None
            and player.current.requested_by == user_id
        ):

            current = player.current

            self._cancel_watcher(
                chat_id
            )

            result = await self.play_next(
                chat_id
            )

            return (
                "current" if result else "stopped",
                current,
            )

        # ----------------------------------------------------
        # OWN QUEUED SONG
        # ----------------------------------------------------

        removed = remove_user_track(
            chat_id,
            user_id,
        )

        if removed is not None:

            await self._delete_track_file(
                removed
            )

            return (
                "queued",
                removed,
            )

        return (
            "denied",
            None,
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

        if player.current is None:
            return False

        self._cancel_watcher(
            chat_id
        )

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

        self._cancel_watcher(
            chat_id
        )

        async with self._lock(
            chat_id
        ):

            player = self._player(
                chat_id
            )

            current = player.current

            ok = await self.audio_stream.stop(
                chat_id
            )

            player.playing = False
            player.paused = False
            player.current = None
            player.loop = False

            if current is not None:

                await self._delete_track_file(
                    current
                )

            if clear:

                queued = list(
                    get_queue(chat_id)
                )

                clear_queue(
                    chat_id
                )

                for track in queued:

                    await self._delete_track_file(
                        track
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

            self._cancel_watcher(
                chat_id
            )

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

            if player.current:

                self._start_watcher(
                    chat_id,
                    player.current,
                )

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
                player and player.playing
            ),
            "paused": bool(
                player and player.paused
            ),
            "loop": bool(
                player and player.loop
            ),
            "current": (
                player.current.to_dict()
                if player and player.current
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

        self._cancel_watcher(
            chat_id
        )

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
                    "Music cleanup failed: %s",
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
