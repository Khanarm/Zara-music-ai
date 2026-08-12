# telegram/client.py

import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient
from telethon.sessions import StringSession

from config import MUSIC_ENABLED

from config import (
    BOT_TOKEN,
    API_ID,
    API_HASH,
    STRING_SESSION,
)


logger = logging.getLogger(__name__)


# ============================================================
# GLOBAL CLIENTS
# ============================================================

bot: Optional[Bot] = None

dp: Optional[Dispatcher] = None

user_client: Optional[TelegramClient] = None

music_calls = None
audio_stream = None
music_player = None
music_downloader = None
music_searcher = None
music_controls = None
voice_receiver = None
voice_music_controller = None


# ============================================================
# AIROGRAM BOT
# ============================================================

def create_bot() -> Bot:
    """
    Create the Telegram Bot API client.
    """

    global bot

    if bot is not None:
        return bot

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not configured."
        )

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML
        ),
    )

    logger.info(
        "Aiogram bot client created."
    )

    return bot


# ============================================================
# DISPATCHER
# ============================================================

def create_dispatcher() -> Dispatcher:
    """
    Create the Aiogram dispatcher.
    """

    global dp

    if dp is not None:
        return dp

    dp = Dispatcher()

    logger.info(
        "Aiogram dispatcher created."
    )

    return dp


# ============================================================
# TELETHON CLIENT
# ============================================================

def create_user_client() -> TelegramClient:
    """
    Create the Telethon client.

    STRING_SESSION is optional.

    If a StringSession is provided, the existing Telegram
    session will be reused.

    Otherwise Telethon will create/use a local session file.
    """

    global user_client

    if user_client is not None:
        return user_client

    if not API_ID:
        raise RuntimeError(
            "API_ID is not configured."
        )

    if not API_HASH:
        raise RuntimeError(
            "API_HASH is not configured."
        )

    if STRING_SESSION:
        session = StringSession(
            STRING_SESSION
        )
    else:
        session = "zara_user"

    user_client = TelegramClient(
        session,
        API_ID,
        API_HASH,
    )

    logger.info(
        "Telethon client created."
    )

    return user_client


# ============================================================
# START BOT
# ============================================================

async def start_bot() -> Bot:
    """
    Initialize the Bot API client.
    """

    client = create_bot()

    await client.delete_webhook(
        drop_pending_updates=False
    )

    me = await client.get_me()

    logger.info(
        "Bot started: @%s (%s)",
        me.username,
        me.id,
    )

    return client


# ============================================================
# START USER CLIENT
# ============================================================

async def start_user_client() -> TelegramClient:
    """
    Start the Telethon user/client session.
    """

    client = create_user_client()

    if not client.is_connected():
        await client.connect()

    if not await client.is_user_authorized():
        logger.warning(
            "Telethon user session is not authorized."
        )

        logger.warning(
            "A Telegram login is required for the user client."
        )

    else:
        me = await client.get_me()

        logger.info(
            "Telethon user client started: @%s (%s)",
            getattr(
                me,
                "username",
                None,
            ),
            me.id,
        )

    return client


# ============================================================
# START ALL TELEGRAM CLIENTS
# ============================================================

async def start_telegram() -> tuple[
    Bot,
    Dispatcher,
    TelegramClient,
]:
    """
    Initialize all Telegram clients and register
    all Aiogram handlers.
    """

    bot_client = await start_bot()

    dispatcher = create_dispatcher()

    # --------------------------------------------------------
    # Register Telegram handlers
    # --------------------------------------------------------

    from telegram.events import (
        router as events_router,
    )

    dispatcher.include_router(
        events_router
    )

    logger.info(
        "Telegram handlers registered."
    )

    # --------------------------------------------------------
    # Start Telethon user client
    # --------------------------------------------------------

    user = await start_user_client()

    logger.info(
        "All Telegram clients initialized."
    )

    if MUSIC_ENABLED:
        try:
            from pytgcalls import PyTgCalls
            from audio.stream import AudioStream
            from music.player import get_player
            from music.downloader import get_downloader
            from music.search import get_searcher
            from music.controls import get_controls
            from music.voice import VoiceMusicController
            from voice.vc_receiver import VoiceChatReceiver
            from pytgcalls import filters as pytg_filters
            global music_calls, audio_stream, music_player, music_downloader, music_searcher, music_controls, voice_receiver, voice_music_controller
            music_calls = PyTgCalls(user)
            audio_stream = AudioStream(user, music_calls)
            await audio_stream.start()
            music_player = get_player(audio_stream)
            music_downloader = get_downloader()
            music_searcher = get_searcher()
            music_controls = get_controls(music_player)
            voice_music_controller = VoiceMusicController(
                bot=bot_client,
                user_client=user,
                player=music_player,
                downloader=music_downloader,
                searcher=music_searcher,
                controls=music_controls,
            )
            voice_receiver = VoiceChatReceiver(
                music_calls,
                user,
                on_transcript=voice_music_controller.handle,
            )
            await voice_receiver.register()

            @music_calls.on_update(pytg_filters.stream_end())
            async def _music_stream_end(_: object, update):
                try:
                    if music_player is not None:
                        await music_player.on_stream_ended(int(update.chat_id))
                except Exception:
                    logger.exception("Music stream-end handler failed")

            logger.info("Music + VC voice command system initialized.")
        except Exception:
            logger.exception("Music system initialization failed.")

    return (
        bot_client,
        dispatcher,
        user,
    )

# ============================================================
# BOT POLLING
# ============================================================

async def start_polling() -> None:
    """
    Start Aiogram polling.

    Event handlers should be registered before this
    function is called.
    """

    bot_client = create_bot()
    dispatcher = create_dispatcher()

    logger.info(
        "Starting Telegram bot polling..."
    )

    await dispatcher.start_polling(
        bot_client
    )


# ============================================================
# MUSIC SERVICES
# ============================================================

def get_music_services():
    if music_player is None or music_downloader is None or music_searcher is None or music_controls is None:
        raise RuntimeError("Music system is not initialized. Set MUSIC_ENABLED=true and start Telegram first.")
    return music_player, music_downloader, music_searcher, music_controls


# ============================================================
# VOICE MUSIC SERVICES
# ============================================================

def get_voice_music_services():
    if voice_receiver is None or voice_music_controller is None:
        raise RuntimeError("VC voice/music system is not initialized.")
    return voice_receiver, voice_music_controller


# ============================================================
# STOP USER CLIENT
# ============================================================

async def stop_user_client() -> None:
    """
    Disconnect Telethon client.
    """

    global user_client

    if user_client is None:
        return

    try:
        if user_client.is_connected():
            await user_client.disconnect()

        logger.info(
            "Telethon user client stopped."
        )

    except Exception:
        logger.exception(
            "Failed to stop Telethon client."
        )

    finally:
        user_client = None


# ============================================================
# STOP BOT
# ============================================================

async def stop_bot() -> None:
    """
    Close Bot API session.
    """

    global bot

    if bot is None:
        return

    try:
        await bot.session.close()

        logger.info(
            "Aiogram bot stopped."
        )

    except Exception:
        logger.exception(
            "Failed to stop Aiogram bot."
        )

    finally:
        bot = None


# ============================================================
# STOP ALL
# ============================================================

async def stop_telegram() -> None:
    """Gracefully stop all Telegram clients and music services."""
    global music_calls, audio_stream, music_player, music_downloader, music_searcher, music_controls, voice_receiver, voice_music_controller
    if voice_receiver is not None:
        try:
            await voice_receiver.cleanup()
        except Exception:
            logger.exception("Failed to cleanup VC voice receiver")
    if music_player is not None:
        try: await music_player.cleanup()
        except Exception: logger.exception("Failed to cleanup music player")
    if audio_stream is not None:
        try: await audio_stream.cleanup()
        except Exception: logger.exception("Failed to cleanup audio stream")
    music_calls = None; audio_stream = None; music_player = None; music_downloader = None; music_searcher = None; music_controls = None; voice_receiver = None; voice_music_controller = None
    await stop_user_client()
    await stop_bot()

    logger.info(
        "All Telegram clients stopped."
    )


# ============================================================
# GETTERS
# ============================================================

def get_bot() -> Bot:
    """
    Return the current Bot instance.
    """

    if bot is None:
        return create_bot()

    return bot


def get_dispatcher() -> Dispatcher:
    """
    Return the current Dispatcher.
    """

    if dp is None:
        return create_dispatcher()

    return dp


def get_user_client() -> TelegramClient:
    """
    Return the Telethon client.
    """

    if user_client is None:
        return create_user_client()

    return user_client


# ============================================================
# CONNECTION STATUS
# ============================================================

async def telegram_health() -> dict:
    """
    Return Telegram connection status.
    """

    result = {
        "bot": False,
        "user_client": False,
        "bot_username": None,
        "user_username": None,
    }

    # --------------------------------------------------------
    # Bot
    # --------------------------------------------------------

    try:
        client = get_bot()

        me = await client.get_me()

        result["bot"] = True

        result["bot_username"] = getattr(
            me,
            "username",
            None,
        )

    except Exception:
        logger.exception(
            "Bot health check failed."
        )

    # --------------------------------------------------------
    # Telethon
    # --------------------------------------------------------

    try:
        client = get_user_client()

        if client.is_connected():

            if await client.is_user_authorized():

                me = await client.get_me()

                result[
                    "user_client"
                ] = True

                result[
                    "user_username"
                ] = getattr(
                    me,
                    "username",
                    None,
                )

    except Exception:
        logger.exception(
            "Telethon health check failed."
        )

    return result


# ============================================================
# CONTEXT MANAGER
# ============================================================

class TelegramManager:
    """
    Convenience manager for starting and stopping
    all Telegram clients.
    """

    def __init__(self) -> None:
        self.bot: Optional[Bot] = None
        self.dispatcher: Optional[Dispatcher] = None
        self.user_client: Optional[
            TelegramClient
        ] = None

    async def start(self) -> None:
        (
            self.bot,
            self.dispatcher,
            self.user_client,
        ) = await start_telegram()

    async def stop(self) -> None:
        await stop_telegram()

        self.bot = None
        self.dispatcher = None
        self.user_client = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        await self.stop()
