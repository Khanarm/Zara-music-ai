from music.player import MusicPlayer
from music.queue import remove_from_queue


class MusicControls:

    def __init__(
        self,
        player: MusicPlayer,
    ):
        self.player = player

    async def play(
        self,
        chat_id: int,
    ):
        if self.player.current(chat_id) is None:
            return await self.player.play_next(chat_id)

        return await self.player.play_current(
            chat_id
        )

    async def pause(
        self,
        chat_id: int,
    ):
        return await self.player.pause(
            chat_id
        )

    async def resume(
        self,
        chat_id: int,
    ):
        return await self.player.resume(
            chat_id
        )

    async def skip(
        self,
        chat_id: int,
    ):
        return await self.player.skip(
            chat_id
        )

    async def skip_for_user(
        self,
        chat_id: int,
        user_id: int,
        is_admin: bool = False,
    ):
        return await self.player.skip_for_user(
            chat_id,
            user_id,
            is_admin,
        )

    async def next(
        self,
        chat_id: int,
    ):
        return await self.skip(chat_id)

    async def stop(
        self,
        chat_id: int,
        clear_queue: bool = False,
    ):
        return await self.player.stop(
            chat_id,
            clear=clear_queue,
        )

    def toggle_loop(
        self,
        chat_id: int,
    ):
        return self.player.toggle_loop(
            chat_id
        )

    def set_loop(
        self,
        chat_id: int,
        enabled: bool,
    ):
        return self.player.set_loop(
            chat_id,
            enabled,
        )

    def queue(
        self,
        chat_id: int,
    ):
        return self.player.get_queue(
            chat_id
        )

    def current(
        self,
        chat_id: int,
    ):
        return self.player.current(
            chat_id
        )

    def status(
        self,
        chat_id: int,
    ):
        return self.player.get_status(
            chat_id
        )

    def remove(
        self,
        chat_id: int,
        index: int,
    ):
        return remove_from_queue(
            chat_id,
            index,
        )

    async def handle(
        self,
        chat_id: int,
        action: str,
    ):

        action = str(
            action
        ).lower().strip()

        if action == "play":
            return await self.play(chat_id)

        if action == "pause":
            return await self.pause(chat_id)

        if action == "resume":
            return await self.resume(chat_id)

        if action in (
            "skip",
            "next",
        ):
            return await self.skip(chat_id)

        if action == "stop":
            return await self.stop(chat_id)

        if action == "stop_clear":
            return await self.stop(
                chat_id,
                True,
            )

        if action == "loop":
            return self.toggle_loop(chat_id)

        if action == "queue":
            return self.queue(chat_id)

        if action == "current":
            return self.current(chat_id)

        if action == "status":
            return self.status(chat_id)

        return None


_controls = None


def get_controls(player):

    global _controls

    if _controls is None:

        _controls = MusicControls(
            player
        )

    return _controls


def reset_controls():

    global _controls

    _controls = None
