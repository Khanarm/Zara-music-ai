# telegram/userbot_join.py

import logging
from typing import Optional

from aiogram import Bot
from telethon import TelegramClient
from telethon.errors import (
    UserAlreadyParticipantError,
    UserBannedInChannelError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    ChannelPrivateError,
    ChatAdminRequiredError,
)
from telethon.tl.functions.channels import (
    JoinChannelRequest,
)
from telethon.tl.functions.messages import (
    ImportChatInviteRequest,
)
from telethon.tl.types import (
    ChannelParticipantBanned,
    ChannelParticipantLeft,
)

logger = logging.getLogger(__name__)


# ============================================================
# RESULT
# ============================================================

class UserbotGroupStatus:

    MEMBER = "member"
    NOT_MEMBER = "not_member"
    BANNED = "banned"
    ERROR = "error"


# ============================================================
# GET USERBOT
# ============================================================

async def _get_userbot(
    user_client: Optional[TelegramClient] = None,
) -> TelegramClient:

    if user_client is not None:
        return user_client

    from telegram.client import get_user_client

    return get_user_client()


# ============================================================
# GET BOT
# ============================================================

async def _get_bot(
    bot: Optional[Bot] = None,
) -> Bot:

    if bot is not None:
        return bot

    from telegram.client import get_bot

    return get_bot()


# ============================================================
# CHECK USERBOT STATUS
# ============================================================

async def check_userbot_group_status(
    chat_id: int,
    user_client: Optional[TelegramClient] = None,
) -> str:

    client = await _get_userbot(
        user_client
    )

    chat_id = int(chat_id)

    try:

        me = await client.get_me()

        if me is None:
            return UserbotGroupStatus.ERROR

        entity = await client.get_entity(
            chat_id
        )

        # ----------------------------------------------------
        # Get participant
        # ----------------------------------------------------

        try:

            participant = await client.get_permissions(
                entity,
                me,
            )

        except Exception as exc:

            logger.warning(
                "Could not get Zara permissions "
                "for chat=%s: %s",
                chat_id,
                exc,
            )

            return UserbotGroupStatus.ERROR

        # ----------------------------------------------------
        # BANNED
        # ----------------------------------------------------

        if getattr(
            participant,
            "is_banned",
            False,
        ):
            return UserbotGroupStatus.BANNED

        # ----------------------------------------------------
        # LEFT / NOT MEMBER
        # ----------------------------------------------------

        if isinstance(
            participant,
            (
                ChannelParticipantBanned,
                ChannelParticipantLeft,
            ),
        ):
            return UserbotGroupStatus.NOT_MEMBER

        # ----------------------------------------------------
        # Normal member/admin/creator
        # ----------------------------------------------------

        return UserbotGroupStatus.MEMBER

    except UserBannedInChannelError:

        return UserbotGroupStatus.BANNED

    except ChannelPrivateError:

        logger.warning(
            "Zara cannot access private group %s.",
            chat_id,
        )

        return UserbotGroupStatus.ERROR

    except Exception:

        logger.exception(
            "Failed checking Zara membership for %s",
            chat_id,
        )

        return UserbotGroupStatus.ERROR


# ============================================================
# CREATE INVITE LINK
# ============================================================

async def create_manager_invite_link(
    chat_id: int,
    bot: Optional[Bot] = None,
) -> Optional[str]:

    manager_bot = await _get_bot(
        bot
    )

    try:

        invite = await manager_bot.create_chat_invite_link(
            chat_id=chat_id,
            name="Zara Userbot Join",
            creates_join_request=False,
        )

        return invite.invite_link

    except ChatAdminRequiredError:

        logger.warning(
            "Manager bot is not admin in group %s.",
            chat_id,
        )

        return None

    except Exception:

        logger.exception(
            "Failed creating invite link for %s",
            chat_id,
        )

        return None


# ============================================================
# JOIN THROUGH INVITE
# ============================================================

async def join_userbot_by_invite(
    invite_link: str,
    user_client: Optional[TelegramClient] = None,
) -> bool:

    client = await _get_userbot(
        user_client
    )

    if not invite_link:
        return False

    try:

        # ----------------------------------------------------
        # Extract invite hash
        # ----------------------------------------------------

        invite_hash = invite_link.rstrip(
            "/"
        ).split("/")[-1]

        if not invite_hash:
            return False

        # ----------------------------------------------------
        # Join private invite
        # ----------------------------------------------------

        result = client(
            ImportChatInviteRequest(
                invite_hash
            )
        )

        await result

        logger.info(
            "Zara joined group through invite."
        )

        return True

    except UserAlreadyParticipantError:

        logger.info(
            "Zara is already a participant."
        )

        return True

    except (
        InviteHashExpiredError,
        InviteHashInvalidError,
    ):

        logger.warning(
            "Invite link is invalid or expired."
        )

        return False

    except UserBannedInChannelError:

        logger.warning(
            "Zara is banned and cannot join."
        )

        return False

    except Exception:

        logger.exception(
            "Zara failed to join through invite."
        )

        return False


# ============================================================
# JOIN PUBLIC GROUP
# ============================================================

async def join_public_group(
    chat_id: int,
    user_client: Optional[TelegramClient] = None,
) -> bool:

    client = await _get_userbot(
        user_client
    )

    try:

        entity = await client.get_entity(
            chat_id
        )

        result = client(
            JoinChannelRequest(
                entity
            )
        )

        await result

        logger.info(
            "Zara joined public group/channel %s.",
            chat_id,
        )

        return True

    except UserAlreadyParticipantError:

        return True

    except UserBannedInChannelError:

        logger.warning(
            "Zara is banned from %s.",
            chat_id,
        )

        return False

    except Exception:

        logger.exception(
            "Public group join failed: %s",
            chat_id,
        )

        return False


# ============================================================
# ENSURE USERBOT IS IN GROUP
# ============================================================

async def ensure_userbot_in_group(
    chat_id: int,
    *,
    bot: Optional[Bot] = None,
    user_client: Optional[TelegramClient] = None,
) -> str:

    chat_id = int(chat_id)

    client = await _get_userbot(
        user_client
    )

    # --------------------------------------------------------
    # First check
    # --------------------------------------------------------

    status = await check_userbot_group_status(
        chat_id,
        client,
    )

    if status == UserbotGroupStatus.MEMBER:

        logger.info(
            "Zara already belongs to group %s.",
            chat_id,
        )

        return UserbotGroupStatus.MEMBER

    if status == UserbotGroupStatus.BANNED:

        logger.warning(
            "Zara is banned from group %s.",
            chat_id,
        )

        return UserbotGroupStatus.BANNED

    if status == UserbotGroupStatus.ERROR:

        return UserbotGroupStatus.ERROR

    # --------------------------------------------------------
    # Not member
    # --------------------------------------------------------

    logger.info(
        "Zara is not a member of %s. "
        "Starting join flow.",
        chat_id,
    )

    # --------------------------------------------------------
    # Try public join first
    # --------------------------------------------------------

    public_joined = await join_public_group(
        chat_id,
        client,
    )

    if public_joined:

        status = await check_userbot_group_status(
            chat_id,
            client,
        )

        if status == UserbotGroupStatus.MEMBER:
            return UserbotGroupStatus.MEMBER

        if status == UserbotGroupStatus.BANNED:
            return UserbotGroupStatus.BANNED

    # --------------------------------------------------------
    # Private/invite-only group
    # --------------------------------------------------------

    invite_link = await create_manager_invite_link(
        chat_id,
        await _get_bot(bot),
    )

    if not invite_link:

        logger.warning(
            "Could not create manager invite link for %s.",
            chat_id,
        )

        return UserbotGroupStatus.ERROR

    joined = await join_userbot_by_invite(
        invite_link,
        client,
    )

    if not joined:

        status = await check_userbot_group_status(
            chat_id,
            client,
        )

        if status == UserbotGroupStatus.BANNED:
            return UserbotGroupStatus.BANNED

        return UserbotGroupStatus.ERROR

    # --------------------------------------------------------
    # Verify after join
    # --------------------------------------------------------

    status = await check_userbot_group_status(
        chat_id,
        client,
    )

    if status == UserbotGroupStatus.MEMBER:

        logger.info(
            "Zara successfully joined group %s.",
            chat_id,
        )

        return UserbotGroupStatus.MEMBER

    if status == UserbotGroupStatus.BANNED:

        return UserbotGroupStatus.BANNED

    return UserbotGroupStatus.ERROR


__all__ = [
    "UserbotGroupStatus",
    "check_userbot_group_status",
    "ensure_userbot_in_group",
]
