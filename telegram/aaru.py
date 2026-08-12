# telegram/aaru.py

import logging
from typing import Optional

from telethon import TelegramClient
from telethon.events import NewMessage

from telegram.client import get_user_client


logger = logging.getLogger(__name__)


# ============================================================
# GLOBAL STATE
# ============================================================

_aaru_client: Optional[TelegramClient] = None

_aaru_started = False


# ============================================================
# GET CLIENT
# ============================================================

def get_aaru_client() -> TelegramClient:
    """
    Return the Telethon client used by Zara/Aaru.
    """

    global _aaru_client

    if _aaru_client is None:
        _aaru_client = get_user_client()

    return _aaru_client


# ============================================================
# BASIC IDENTITY
# ============================================================

async def get_aaru_identity() -> Optional[dict]:
    """
    Return the current Telegram user identity.
    """

    client = get_aaru_client()

    try:
        if not client.is_connected():
            await client.connect()

        if not await client.is_user_authorized():
            logger.warning(
                "Aaru Telegram session is not authorized."
            )

            return None

        me = await client.get_me()

        return {
            "id": me.id,
            "username": getattr(
                me,
                "username",
                None,
            ),
            "first_name": getattr(
                me,
                "first_name",
                None,
            ),
            "last_name": getattr(
                me,
                "last_name",
                None,
            ),
            "phone": getattr(
                me,
                "phone",
                None,
            ),
        }

    except Exception:
        logger.exception(
            "Failed to get Aaru identity."
        )

        return None


# ============================================================
# AUTHORIZATION CHECK
# ============================================================

async def is_aaru_authorized() -> bool:
    """
    Check whether the Telethon session is authorized.
    """

    client = get_aaru_client()

    try:

        if not client.is_connected():
            await client.connect()

        return await client.is_user_authorized()

    except Exception:

        logger.exception(
            "Aaru authorization check failed."
        )

        return False


# ============================================================
# SEND MESSAGE
# ============================================================

async def send_message(
    entity,
    text: str,
    **kwargs,
):
    """
    Send a message through the Aaru user client.
    """

    if not text:
        return None

    client = get_aaru_client()

    try:

        return await client.send_message(
            entity,
            text,
            **kwargs,
        )

    except Exception:

        logger.exception(
            "Aaru failed to send message."
        )

        return None


# ============================================================
# GET ENTITY
# ============================================================

async def get_entity(
    entity,
):
    """
    Resolve a Telegram username, ID or entity.
    """

    client = get_aaru_client()

    try:

        return await client.get_entity(
            entity
        )

    except Exception:

        logger.exception(
            "Failed to resolve Telegram entity: %s",
            entity,
        )

        return None


# ============================================================
# GET CHAT
# ============================================================

async def get_chat(
    chat_id: int,
):
    """
    Get Telegram chat/entity information.
    """

    return await get_entity(
        chat_id
    )


# ============================================================
# MESSAGE HISTORY
# ============================================================

async def get_messages(
    entity,
    limit: int = 20,
):
    """
    Fetch recent messages from a Telegram chat.
    """

    client = get_aaru_client()

    limit = max(
        1,
        min(
            int(limit),
            100,
        ),
    )

    try:

        return await client.get_messages(
            entity,
            limit=limit,
        )

    except Exception:

        logger.exception(
            "Failed to fetch Telegram messages."
        )

        return []


# ============================================================
# EVENT HANDLER
# ============================================================

async def handle_new_message(
    event,
) -> None:
    """
    Basic Telethon message handler.

    Actual AI processing remains in the AI layer.
    """

    try:

        message = event.message

        if not message:
            return

        text = (
            getattr(
                message,
                "message",
                None,
            )
            or ""
        ).strip()

        if not text:
            return

        logger.debug(
            "Aaru received message: %s",
            text[:100],
        )

        # ----------------------------------------------------
        # IMPORTANT
        # ----------------------------------------------------
        #
        # AI response generation is NOT done here yet.
        #
        # This event layer only receives Telethon messages.
        # The AI brain will be connected after the AI module
        # is finalized.
        #

    except Exception:

        logger.exception(
            "Aaru new-message handler failed."
        )


# ============================================================
# REGISTER EVENTS
# ============================================================

def register_events() -> None:
    """
    Register Telethon event handlers.
    """

    client = get_aaru_client()

    # Prevent duplicate registration.
    if getattr(
        client,
        "_zara_events_registered",
        False,
    ):
        logger.debug(
            "Aaru events are already registered."
        )

        return

    client.add_event_handler(
        handle_new_message,
        NewMessage(
            incoming=True
        ),
    )

    client._zara_events_registered = True

    logger.info(
        "Aaru Telethon events registered."
    )


# ============================================================
# START
# ============================================================

async def start_aaru() -> TelegramClient:
    """
    Start the Aaru user client and register events.
    """

    global _aaru_started

    client = get_aaru_client()

    if not client.is_connected():
        await client.connect()

    authorized = (
        await client.is_user_authorized()
    )

    if not authorized:

        logger.warning(
            "Aaru client is connected but not authorized."
        )

        _aaru_started = False

        return client

    register_events()

    identity = (
        await get_aaru_identity()
    )

    if identity:

        username = (
            identity.get(
                "username"
            )
            or "unknown"
        )

        logger.info(
            "Aaru started successfully: @%s",
            username,
        )

    _aaru_started = True

    return client


# ============================================================
# STOP
# ============================================================

async def stop_aaru() -> None:
    """
    Stop the Aaru user client.
    """

    global _aaru_started

    client = get_aaru_client()

    try:

        if client.is_connected():
            await client.disconnect()

        logger.info(
            "Aaru client stopped."
        )

    except Exception:

        logger.exception(
            "Failed to stop Aaru client."
        )

    finally:

        _aaru_started = False


# ============================================================
# STATUS
# ============================================================

async def get_aaru_status() -> dict:
    """
    Return Aaru client status.
    """

    client = get_aaru_client()

    connected = False
    authorized = False

    try:

        connected = client.is_connected()

        if connected:
            authorized = (
                await client.is_user_authorized()
            )

    except Exception:

        logger.exception(
            "Failed to check Aaru status."
        )

    identity = None

    if authorized:
        identity = (
            await get_aaru_identity()
        )

    return {
        "started": _aaru_started,
        "connected": connected,
        "authorized": authorized,
        "identity": identity,
    }


# ============================================================
# RUN UNTIL DISCONNECTED
# ============================================================

async def run_aaru() -> None:
    """
    Keep the Telethon client running.

    Normally main.py will manage the application lifecycle,
    so this function should only be used when a dedicated
    Telethon task is required.
    """

    client = await start_aaru()

    if not await client.is_user_authorized():

        logger.warning(
            "Aaru cannot run because the Telegram session "
            "is not authorized."
        )

        return

    logger.info(
        "Aaru is running."
    )

    await client.run_until_disconnected()
