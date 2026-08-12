# telegram/manager_bot.py

import logging
from typing import Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import OWNER_ID

from telegram.client import (
    get_bot,
    get_user_client,
    telegram_health,
)


logger = logging.getLogger(__name__)

router = Router()


# ============================================================
# PERMISSION HELPERS
# ============================================================

def is_owner(
    user_id: Optional[int],
) -> bool:
    """
    Check whether a Telegram user is the configured owner.
    """

    if not user_id:
        return False

    try:
        return int(user_id) == int(
            OWNER_ID
        )
    except (TypeError, ValueError):
        return False


def owner_only(
    message: Message,
) -> bool:
    """
    Check owner permission for a message.
    """

    if not message.from_user:
        return False

    return is_owner(
        message.from_user.id
    )


async def owner_required(
    message: Message,
) -> bool:
    """
    Send permission error when user is not owner.
    """

    if owner_only(
        message
    ):
        return True

    try:
        await message.answer(
            "⛔ Ye command sirf bot owner use kar sakta hai."
        )
    except Exception:
        logger.exception(
            "Failed to send owner permission message."
        )

    return False


# ============================================================
# /start
# ============================================================

@router.message(
    Command("start")
)
async def start_command(
    message: Message,
) -> None:
    """
    Basic /start command.
    """

    if not message.from_user:
        return

    name = (
        message.from_user.first_name
        or "Bhai"
    )

    await message.answer(
        f"👋 Hello {name}!\n\n"
        "Main Zara AI hoon.\n"
        "Tum mujhse normal chat, questions aur available "
        "features ke baare mein baat kar sakte ho.\n\n"
        "💡 /help - Help"
    )


# ============================================================
# /help
# ============================================================

@router.message(
    Command("help")
)
async def help_command(
    message: Message,
) -> None:
    """
    Show basic bot help.
    """

    text = (
        "🤖 <b>Zara AI Help</b>\n\n"
        "Tum Zara se normal conversation kar sakte ho.\n\n"
        "<b>Basic commands:</b>\n"
        "/start - Start Zara\n"
        "/help - Help\n"
        "/status - Bot status\n\n"
        "<b>Music:</b>\n"
        "Music features available hone ke baad "
        "play, pause, resume, skip aur queue commands "
        "available honge.\n\n"
        "<b>Voice:</b>\n"
        "Voice AI processing bhi supported architecture "
        "me hai."
    )

    await message.answer(
        text
    )


# ============================================================
# /status
# ============================================================

@router.message(
    Command("status")
)
async def status_command(
    message: Message,
) -> None:
    """
    Show Telegram connection status.

    Owner can see detailed status.
    Normal users get a simple status.
    """

    if not message.from_user:
        return

    try:
        health = await telegram_health()

        bot_status = (
            "🟢 Online"
            if health.get("bot")
            else "🔴 Offline"
        )

        user_status = (
            "🟢 Connected"
            if health.get("user_client")
            else "🔴 Not connected"
        )

        if owner_only(
            message
        ):

            bot_username = (
                health.get(
                    "bot_username"
                )
                or "Unknown"
            )

            user_username = (
                health.get(
                    "user_username"
                )
                or "Not logged in"
            )

            text = (
                "📊 <b>Zara Status</b>\n\n"
                f"🤖 Bot: {bot_status}\n"
                f"👤 Bot username: @{bot_username}\n"
                f"📡 User client: {user_status}\n"
                f"👤 User username: @{user_username}"
            )

        else:

            text = (
                "📊 <b>Zara Status</b>\n\n"
                f"🤖 Bot: {bot_status}\n"
                "🧠 AI system: Ready"
            )

        await message.answer(
            text
        )

    except Exception:

        logger.exception(
            "Status command failed."
        )

        await message.answer(
            "⚠️ Status check failed."
        )


# ============================================================
# /id
# ============================================================

@router.message(
    Command("id")
)
async def id_command(
    message: Message,
) -> None:
    """
    Show current Telegram user/chat IDs.
    """

    if not message.from_user:
        return

    text = (
        "🆔 <b>Telegram IDs</b>\n\n"
        f"User ID: <code>{message.from_user.id}</code>\n"
        f"Chat ID: <code>{message.chat.id}</code>"
    )

    await message.answer(
        text
    )


# ============================================================
# /owner
# ============================================================

@router.message(
    Command("owner")
)
async def owner_command(
    message: Message,
) -> None:
    """
    Show whether current user is the owner.
    """

    if not message.from_user:
        return

    if owner_only(
        message
    ):
        await message.answer(
            "👑 Haan bhai, tum Zara ke owner ho."
        )
    else:
        await message.answer(
            "ℹ️ Ye information available nahi hai."
        )


# ============================================================
# /admin
# ============================================================

@router.message(
    Command("admin")
)
async def admin_command(
    message: Message,
) -> None:
    """
    Owner-only admin panel entry point.

    Detailed admin functions can be added later.
    """

    if not await owner_required(
        message
    ):
        return

    await message.answer(
        "👑 <b>Zara Admin</b>\n\n"
        "Admin system active hai.\n\n"
        "Available:\n"
        "• /status\n"
        "• /broadcast\n"
        "• /users\n"
        "• /groups"
    )


# ============================================================
# /users
# ============================================================

@router.message(
    Command("users")
)
async def users_command(
    message: Message,
) -> None:
    """
    Placeholder for user statistics.
    """

    if not await owner_required(
        message
    ):
        return

    # Database statistics will be connected
    # after database/users.py is finalized.

    await message.answer(
        "👥 User statistics module database ke saath "
        "next stage me connect hoga."
    )


# ============================================================
# /groups
# ============================================================

@router.message(
    Command("groups")
)
async def groups_command(
    message: Message,
) -> None:
    """
    Placeholder for group statistics.
    """

    if not await owner_required(
        message
    ):
        return

    await message.answer(
        "👥 Group management module database ke saath "
        "next stage me connect hoga."
    )


# ============================================================
# /broadcast
# ============================================================

@router.message(
    Command("broadcast")
)
async def broadcast_command(
    message: Message,
) -> None:
    """
    Owner-only broadcast placeholder.

    Actual database-backed broadcast system will be added
    after users.py is finalized.
    """

    if not await owner_required(
        message
    ):
        return

    await message.answer(
        "📢 Broadcast system abhi database users list "
        "ke saath connect nahi hua hai."
    )


# ============================================================
# /restart
# ============================================================

@router.message(
    Command("restart")
)
async def restart_command(
    message: Message,
) -> None:
    """
    Informational restart command.

    The actual process restart should be handled by
    Railway/Docker process management instead of letting
    the bot terminate itself.
    """

    if not await owner_required(
        message
    ):
        return

    await message.answer(
        "🔄 Restart request received.\n\n"
        "Production me process restart Railway/Docker "
        "handle karega."
    )


# ============================================================
# /ping
# ============================================================

@router.message(
    Command("ping")
)
async def ping_command(
    message: Message,
) -> None:
    """
    Simple latency/availability test.
    """

    await message.answer(
        "🏓 Pong!"
    )


# ============================================================
# REGISTER
# ============================================================

def register_manager_handlers(
    dispatcher,
) -> None:
    """
    Register manager/owner handlers.
    """

    dispatcher.include_router(
        router
    )

    logger.info(
        "Manager bot handlers registered."
    )
