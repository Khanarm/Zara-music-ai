# telegram/events.py

import asyncio
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from ai.brain import chat

from ai.intent import (
    detect_intent,
    is_music_intent,
    MUSIC_PLAY,
    MUSIC_SEARCH,
    MUSIC_VIDEO,
    MUSIC_PAUSE,
    MUSIC_RESUME,
    MUSIC_SKIP,
    MUSIC_STOP,
    MUSIC_QUEUE,
    MUSIC_REMOVE,
)

from database.users import (
    get_user,
    create_user,
)

from database.groups import (
    get_group,
    get_or_create_group,
)

from config import (
    OWNER_ID,
    MUSIC_MAX_QUEUE,
)


logger = logging.getLogger(__name__)

router = Router()


# ============================================================
# ZARA USERBOT GROUP ACCESS
# ============================================================

async def ensure_zara_in_group(
    message: Message,
) -> bool:
    """
    Make sure Zara Userbot can access the group.

    Returns:
        True  -> Zara can join/use the group.
        False -> Zara cannot access the group.
    """

    if not message.chat:
        return False

    chat_id = int(message.chat.id)

    try:
        from telegram.client import get_user_client

        user_client = get_user_client()

        # ----------------------------------------------------
        # Get Zara Userbot identity
        # ----------------------------------------------------

        zara = await user_client.get_me()

        if not zara:
            logger.error(
                "Could not get Zara Userbot identity."
            )
            return False

        zara_id = int(zara.id)

        # ----------------------------------------------------
        # Check Zara membership using Manager Bot
        # ----------------------------------------------------

        try:

            member = await message.bot.get_chat_member(
                chat_id,
                zara_id,
            )

            status = str(
                member.status
            ).lower()

            # Zara is banned.
            if status in {
                "kicked",
                "banned",
            }:

                await message.bot.send_message(
                    chat_id,
                    "❌ Zara is banned from this group.\n\n"
                    "Please unban Zara Userbot first, then try "
                    "/play again.",
                )

                logger.warning(
                    "Zara Userbot is banned from group %s",
                    chat_id,
                )

                return False

            # Zara is already inside.
            if status in {
                "member",
                "administrator",
                "creator",
                "owner",
            }:

                logger.info(
                    "Zara Userbot is already in group %s",
                    chat_id,
                )

                return True

        except Exception:

            logger.debug(
                "Manager bot could not check Zara membership.",
                exc_info=True,
            )

        # ----------------------------------------------------
        # Zara is not currently inside.
        #
        # Create invite link using Manager Bot.
        # ----------------------------------------------------

        try:

            invite = await message.bot.create_chat_invite_link(
                chat_id=chat_id,
                name="Zara Userbot",
                creates_join_request=False,
            )

            invite_link = invite.invite_link

        except Exception:

            logger.exception(
                "Could not create invite link for Zara."
            )

            await message.bot.send_message(
                chat_id,
                "❌ Zara is not in this group.\n\n"
                "Please add Zara Userbot to this group "
                "and give it permission to join the voice chat.",
            )

            return False

        # ----------------------------------------------------
        # Userbot joins using invite link.
        # ----------------------------------------------------

        try:

            from telethon.tl.functions.messages import (
                ImportChatInviteRequest,
            )

            # Extract invite hash.
            if "/+" in invite_link:

                invite_hash = invite_link.split(
                    "/+",
                    1,
                )[1]

            else:

                invite_hash = invite_link.rsplit(
                    "/",
                    1,
                )[-1]

            if not invite_hash:

                raise RuntimeError(
                    "Invalid Telegram invite link."
                )

            await user_client(
                ImportChatInviteRequest(
                    invite_hash
                )
            )

            logger.info(
                "Zara Userbot joined group %s using invite link.",
                chat_id,
            )

            return True

        except Exception as exc:

            logger.warning(
                "Zara Userbot could not join group %s: %s",
                chat_id,
                exc,
                exc_info=True,
            )

            # ------------------------------------------------
            # Final English instruction.
            # ------------------------------------------------

            await message.bot.send_message(
                chat_id,
                "❌ Zara could not join this group.\n\n"
                "Please add Zara Userbot to the group manually "
                "and make sure it is not banned or restricted.",
            )

            return False

    except Exception:
        logger.exception(
            "Failed to prepare Zara Userbot access for group %s",
            chat_id,
        )
        try:
            await message.bot.send_message(
                chat_id,
                "❌ Zara could not access this group.\n\n"
                "Please make sure Zara Userbot is not banned or restricted "
                "and that the Manager Bot has permission to invite users.",
            )
        except Exception:
            logger.debug(
                "Could not send Zara access error message.",
                exc_info=True,
            )
        return False

# ============================================================
# USER HELPERS
# ============================================================

async def ensure_user(
    message: Message,
) -> Optional[dict]:
    """
    Make sure Telegram user exists in MongoDB.
    """

    if not message.from_user:
        return None

    user_id = message.from_user.id

    try:
        user = await get_user(
            user_id
        )

        if user:
            return user

        return await create_user(
            user_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )

    except Exception:
        logger.exception(
            "Failed to ensure user %s",
            user_id,
        )

        return None


# ============================================================
# GROUP HELPERS
# ============================================================

def is_group_message(
    message: Message,
) -> bool:
    """
    Check whether message was sent inside a group.
    """

    if not message.chat:
        return False

    return message.chat.type in {
        "group",
        "supergroup",
    }


async def get_group_settings(
    chat_id: int,
) -> Optional[dict]:
    """
    Get stored group settings.
    """

    try:
        return await get_group(
            chat_id
        )

    except Exception:
        logger.exception(
            "Failed to get group settings: %s",
            chat_id,
        )

        return None


# ============================================================
# MENTION DETECTION
# ============================================================

def bot_is_mentioned(
    message: Message,
) -> bool:
    """
    Detect @mention in message.
    """

    text = (
        message.text
        or message.caption
        or ""
    ).lower()

    if not text:
        return False

    entities = (
        message.entities
        or message.caption_entities
        or []
    )

    for entity in entities:

        if entity.type != "mention":
            continue

        try:
            username = text[
                entity.offset:
                entity.offset + entity.length
            ]

            if username.startswith("@"):
                return True

        except Exception:
            continue

    return False


def is_reply_to_bot(
    message: Message,
) -> bool:
    """
    Check whether message is replying to a bot message.
    """

    replied = message.reply_to_message

    if not replied:
        return False

    if not replied.from_user:
        return False

    return replied.from_user.is_bot


# ============================================================
# GROUP AI PERMISSION
# ============================================================

def should_answer_group(
    message: Message,
    group_settings: Optional[dict],
) -> bool:
    """
    Decide whether Zara should answer normal AI messages
    inside a group.

    Music commands are handled separately and do not require
    mention/reply.
    """

    if not group_settings:
        return True

    if group_settings.get(
        "ai_enabled",
        True,
    ) is False:
        return False

    reply_to_all = group_settings.get(
        "reply_to_all",
        False,
    )

    if reply_to_all:
        return True

    if bot_is_mentioned(
        message
    ):
        return True

    if is_reply_to_bot(
        message
    ):
        return True

    return False


# ============================================================
# REPLY CONTEXT
# ============================================================

async def get_reply_context(
    message: Message,
) -> Optional[str]:
    """
    Get text/caption from replied message.
    """

    reply = message.reply_to_message

    if not reply:
        return None

    return (
        reply.text
        or reply.caption
        or None
    )


# ============================================================
# CLEAN MESSAGE
# ============================================================

def clean_message_text(
    message: Message,
) -> str:
    """
    Clean Telegram message text.

    Removes @mentions from the text.
    """

    text = (
        message.text
        or message.caption
        or ""
    ).strip()

    if not text:
        return ""

    words = text.split()

    cleaned = []

    for word in words:

        if word.startswith("@"):
            continue

        cleaned.append(word)

    return " ".join(
        cleaned
    ).strip()


# ============================================================
# MUSIC SERVICES
# ============================================================

async def _music_services():
    """
    Get normal music services.
    """

    from telegram.client import (
        get_music_services,
    )

    return get_music_services()


# ============================================================
# MUSIC HANDLER
# ============================================================

async def handle_music_intent(
    message: Message,
    intent: str,
) -> bool:
    """Handle text music commands with a fast request flow."""

    if not message.from_user or not message.chat:
        return False

    processing = None

    try:
        (
            player,
            downloader,
            searcher,
            controls,
        ) = await _music_services()

        chat_id = message.chat.id
        user_id = message.from_user.id
        text = clean_message_text(message)

        # Music command messages only are deleted.
        try:
            await message.delete()
        except Exception:
            logger.debug("Could not delete music command message.", exc_info=True)

        # Send this before search/download/VC work.
        try:
            processing = await message.answer("🎵 Processing...")
        except Exception:
            processing = None


        # ====================================================
        # PLAY / SEARCH / VIDEO
        # ====================================================

        if intent in {
            MUSIC_SEARCH,
            MUSIC_PLAY,
            MUSIC_VIDEO,
        }:

            query = text

            prefixes = (
                "search song",
                "song search",
                "gana search",
                "gaana search",
                "music search",
                "find song",
                "find music",
                "search music",
                "play song",
                "play music",
                "play",
                "chalao",
                "chala",
                "bajao",
                "baja do",
                "song chala",
                "gana chala",
                "gaana chala",
                "video chalao",
                "video bajao",
                "video play",
                "video dikhao",
            )

            lowered = query.lower()

            for prefix in prefixes:

                if lowered.startswith(prefix):

                    query = query[
                        len(prefix):
                    ].strip(" :-")

                    break

            # ------------------------------------------------
            # PLAY CURRENT
            # ------------------------------------------------

            if not query:

                current = player.current(
                    chat_id
                )

                if (
                    current
                    and intent == MUSIC_PLAY
                ):

                    # Make sure Zara can access group.
                    zara_ready = (
                        await ensure_zara_in_group(
                            message
                        )
                    )

                    if not zara_ready:

                        if processing:

                            try:
                                await processing.delete()
                            except Exception:
                                pass

                        return True

                    ok = await player.play_current(
                        chat_id
                    )

                    if processing:

                        try:
                            await processing.delete()
                        except Exception:
                            pass

                    await message.bot.send_message(
                        chat_id,
                        (
                            "▶️ Playing current song."
                            if ok
                            else
                            "❌ Could not start playback."
                        ),
                    )

                    return True

                if processing:

                    try:
                        await processing.delete()
                    except Exception:
                        pass

                await message.bot.send_message(
                    chat_id,
                    "🎵 Song ka naam batao.",
                )

                return True

            # ------------------------------------------------
            # QUEUE LIMIT
            # ------------------------------------------------

            try:

                max_queue = int(
                    MUSIC_MAX_QUEUE
                )

            except Exception:

                max_queue = 10

            if (
                player.queue_size(
                    chat_id
                ) >= max_queue
            ):

                if processing:

                    try:
                        await processing.delete()
                    except Exception:
                        pass

                await message.bot.send_message(
                    chat_id,
                    "⚠️ Music queue is full.",
                )

                return True

            # ------------------------------------------------
            # MAKE SURE ZARA IS IN GROUP
            # ------------------------------------------------

            zara_ready = (
                await ensure_zara_in_group(
                    message
                )
            )

            if not zara_ready:

                if processing:

                    try:
                        await processing.delete()
                    except Exception:
                        pass

                return True

            # ------------------------------------------------
            # VC JOIN + SEARCH PARALLEL
            # ------------------------------------------------

            join_task = None

            try:

                from telegram.client import (
                    get_voice_music_services,
                )

                receiver, _controller = (
                    get_voice_music_services()
                )

                join_task = asyncio.create_task(
                    receiver.join(
                        chat_id
                    )
                )

            except Exception:

                logger.debug(
                    "VC join task could not be started.",
                    exc_info=True,
                )

            # ------------------------------------------------
            # SEARCH
            # ------------------------------------------------

            try:

                result = await searcher.first(
                    query
                )

            except Exception:

                logger.exception(
                    "Music search failed: %s",
                    query,
                )

                if join_task:

                    join_task.cancel()

                if processing:

                    try:
                        await processing.delete()
                    except Exception:
                        pass

                await message.bot.send_message(
                    chat_id,
                    "❌ Song search me error aa gaya.",
                )

                return True

            # ------------------------------------------------
            # SEARCH RESULT NOT FOUND
            # ------------------------------------------------

            if not result:

                if join_task:

                    join_task.cancel()

                if processing:

                    try:
                        await processing.delete()
                    except Exception:
                        pass

                await message.bot.send_message(
                    chat_id,
                    f"❌ <b>{query}</b> nahi mila.",
                )

                return True

            # ------------------------------------------------
            # DOWNLOAD
            # ------------------------------------------------

            is_video = (
                intent == MUSIC_VIDEO
            )

            try:

                if is_video:

                    try:

                        path = await downloader.download(
                            result,
                            video=True,
                        )

                    except TypeError:

                        path = await downloader.download(
                            result
                        )

                else:

                    path = await downloader.download(
                        result
                    )

            except Exception:

                logger.exception(
                    "Music download failed: %s",
                    result.title,
                )

                if join_task:

                    join_task.cancel()

                if processing:

                    try:
                        await processing.delete()
                    except Exception:
                        pass

                await message.bot.send_message(
                    chat_id,
                    "❌ Song download nahi ho paya.",
                )

                return True

            # ------------------------------------------------
            # DOWNLOAD FAILED
            # ------------------------------------------------

            if not path:

                if join_task:

                    join_task.cancel()

                if processing:

                    try:
                        await processing.delete()
                    except Exception:
                        pass

                await message.bot.send_message(
                    chat_id,
                    "❌ Song/media download nahi ho paya.",
                )

                return True

            # ------------------------------------------------
            # CREATE TRACK
            # ------------------------------------------------

            from music.queue import Track

            metadata = dict(
                getattr(
                    result,
                    "metadata",
                    {},
                )
                or {}
            )

            metadata[
                "telegram_message"
            ] = None

            track = Track(
                title=result.title,
                url=result.url,
                audio_url=result.url,
                audio_path=path,
                duration=result.duration,
                requested_by=user_id,
                requested_by_name=(
                    message.from_user.full_name
                ),
                thumbnail=getattr(
                    result,
                    "thumbnail",
                    None,
                ),
                source=getattr(
                    result,
                    "source",
                    None,
                ),
                media_type=(
                    "video"
                    if is_video
                    else "audio"
                ),
                metadata=metadata,
            )

            
            # ------------------------------------------------
            # WAIT FOR VC JOIN
            # ------------------------------------------------

            if join_task:

                try:
                    joined = await join_task

                except Exception:
                    logger.exception("VC join failed.")
                    joined = False

                if not joined:
                    try:
                        await downloader.delete(path)
                    except Exception:
                        logger.debug(
                            "Failed cleaning downloaded file after VC join failure.",
                            exc_info=True,
                        )

                    if processing:
                        try:
                            await processing.delete()
                        except Exception:
                            pass

                    reason = "join_failed"

                    try:
                        from telegram.client import get_voice_music_services

                        receiver, _controller = get_voice_music_services()
                        active = await receiver.has_active_call(chat_id)

                        if not active:
                            reason = "no_active_call"

                    except Exception:
                        logger.debug(
                            "Could not determine VC join failure reason.",
                            exc_info=True,
                        )

                    if reason == "no_active_call":
                        response = (
                            "❌ <b>No active voice chat found.</b>\n\n"
                            "Please start a voice chat first, then try playing "
                            "the song again."
                        )
                    else:
                        response = (
                            "❌ <b>Zara could not join the voice chat.</b>\n\n"
                            "Please make sure Zara is in the group, is not banned "
                            "or restricted, and has permission to join the voice chat."
                        )

                    await message.bot.send_message(
                        chat_id,
                        response,
                    )
                    return True

            else:
                try:
                    await downloader.delete(path)
                except Exception:
                    pass

                if processing:
                    try:
                        await processing.delete()
                    except Exception:
                        pass

                await message.bot.send_message(
                    chat_id,
                    "❌ <b>Zara voice chat system is unavailable.</b>",
                )
                return True

            # ------------------------------------------------
            # ADD TO PLAYER
            # ------------------------------------------------

            was_playing = (
                player.is_playing(
                    chat_id
                )
            )

            position = await player.add(
                chat_id,
                track,
                play_now=not was_playing,
            )

            # ------------------------------------------------
            # PLAYBACK FAILURE
            # ------------------------------------------------

            if (
                not was_playing
                and (
                    player.current(chat_id)
                    is None
                    or not player.is_playing(
                        chat_id
                    )
                )
            ):

                if processing:

                    try:
                        await processing.delete()
                    except Exception:
                        pass

                try:

                    await downloader.delete(
                        path
                    )

                except Exception:

                    logger.debug(
                        "Failed cleaning media "
                        "after playback failure.",
                        exc_info=True,
                    )

                await message.bot.send_message(
                    chat_id,
                    "❌ Song ready tha, lekin VC playback start nahi hua.",
                )

                return True

            # ------------------------------------------------
            # REMOVE PROCESSING
            # ------------------------------------------------

            if processing:

                try:
                    await processing.delete()
                except Exception:
                    pass

            # ------------------------------------------------
            # RESPONSE
            # ------------------------------------------------

            if was_playing:

                await message.bot.send_message(
                    chat_id,
                    f"🎵 <b>{result.title}</b>\n"
                    f"🎵 Play by Zara Music\n"
                    f"👤 Requested by: "
                    f"<b>{message.from_user.full_name}</b>\n"
                    f"⏭️ Queue position: "
                    f"<b>{position}</b>",
                )

            else:

                await message.bot.send_message(
                    chat_id,
                    f"🎵 <b>{result.title}</b>\n"
                    f"🎵 Play by Zara Music\n"
                    f"👤 Requested by: "
                    f"<b>{message.from_user.full_name}</b>",
                )

            return True        
        
        # ====================================================
        # PAUSE / RESUME
        # ====================================================
        if intent == MUSIC_PAUSE:
            ok = await controls.pause(chat_id)
            if processing:
                try: await processing.delete()
                except Exception: pass
            await message.bot.send_message(chat_id, "⏸️ Paused." if ok else "⚠️ Pause is not supported.")
            return True

        if intent == MUSIC_RESUME:
            ok = await controls.resume(chat_id)
            if processing:
                try: await processing.delete()
                except Exception: pass
            await message.bot.send_message(chat_id, "▶️ Resumed." if ok else "❌ Nothing to resume.")
            return True

        # ====================================================
        # REQUESTER-AWARE SKIP
        # ====================================================
        if intent == MUSIC_SKIP:
            is_admin = user_id == OWNER_ID
            if not is_admin:
                try:
                    member = await message.bot.get_chat_member(chat_id, user_id)
                    is_admin = str(member.status).lower() in {"administrator", "creator", "owner"}
                except Exception:
                    is_admin = False

            result_type = await player.skip_for_user(
                chat_id,
                user_id,
                is_admin=is_admin,
            )

            if processing:
                try: await processing.delete()
                except Exception: pass

            if result_type == "current":
                text_out = "⏭️ Current song skipped."
            elif result_type == "queued":
                text_out = "⏭️ Your queued song was removed."
            elif result_type == "stopped":
                text_out = "⏭️ Current song skipped. Queue is empty."
            elif result_type == "empty":
                text_out = "📭 Nothing is playing."
            else:
                text_out = "⛔ You can only skip your own requested song."

            await message.bot.send_message(chat_id, text_out)
            return True

        # ====================================================
        # STOP
        # ====================================================
        if intent == MUSIC_STOP:
            await controls.stop(chat_id, True)
            if processing:
                try: await processing.delete()
                except Exception: pass
            await message.bot.send_message(chat_id, "⏹️ Music stopped aur queue clear kar di.")
            return True

        # ====================================================
        # QUEUE
        # ====================================================
        if intent == MUSIC_QUEUE:
            q = controls.queue(chat_id)
            current = player.current(chat_id)
            if processing:
                try: await processing.delete()
                except Exception: pass
            if not q and not current:
                await message.bot.send_message(chat_id, "📭 Queue empty hai.")
                return True
            lines = ["🎵 <b>Zara Music Queue</b>"]
            if current:
                lines.append(
                    f"▶️ Now: <b>{current.title}</b> — {current.requested_by_name or 'User'}"
                )
            for i, track in enumerate(q, 1):
                lines.append(
                    f"{i}. <b>{track.title}</b> — {track.requested_by_name or 'User'}"
                )
            await message.bot.send_message(chat_id, "\n".join(lines[:31]))
            return True

        # ====================================================
        # REMOVE
        # ====================================================
        if intent == MUSIC_REMOVE:
            q = controls.queue(chat_id)
            if processing:
                try: await processing.delete()
                except Exception: pass
            if not q:
                await message.bot.send_message(chat_id, "📭 Queue empty hai.")
                return True
            removed = controls.remove(chat_id, 0)
            if removed and removed.audio_path:
                try:
                    await downloader.delete(removed.audio_path)
                except Exception:
                    logger.debug("Failed to cleanup removed track file.", exc_info=True)
            await message.bot.send_message(
                chat_id,
                f"🗑️ Removed: <b>{removed.title}</b>" if removed else "❌ Song remove nahi hua.",
            )
            return True

    except Exception:
        logger.exception("Music handler failed")
        if processing:
            try: await processing.delete()
            except Exception: pass
        try:
            await message.bot.send_message(
                message.chat.id,
                "❌ Music system me error aa gaya.",
            )
        except Exception:
            pass
        return True

    return False


# ============================================================
# VC ADMIN
# ============================================================

def _is_admin_status(
    status: str,
) -> bool:

    return status in {
        "administrator",
        "creator",
        "owner",
    }


async def _group_admin(
    bot,
    chat_id: int,
    user_id: int,
) -> bool:

    if user_id == OWNER_ID:
        return True

    try:

        member = await bot.get_chat_member(
            chat_id,
            user_id,
        )

        return _is_admin_status(
            str(
                member.status
            ).lower()
        )

    except Exception:

        return False


# ============================================================
# /JOIN
# ============================================================

@router.message(
    Command("join")
)
async def join_voice_chat(
    message: Message,
) -> None:

    if not message.from_user:
        return

    if not message.chat:
        return

    if not is_group_message(
        message
    ):
        return

    if not await _group_admin(
        message.bot,
        message.chat.id,
        message.from_user.id,
    ):

        await message.answer(
            "⛔ Sirf group admin/owner "
            "Zara ko VC me join kara sakta hai."
        )

        return

    try:

        from telegram.client import (
            get_voice_music_services,
        )

        receiver, _ = (
            get_voice_music_services()
        )

        ok = await receiver.join(
            message.chat.id
        )

        if ok:

            await message.answer(
                "🎙️ Zara VC me join ho gayi."
            )

        else:

            await message.answer(
                "❌ Active Voice Chat nahi mila.\n\n"
                "Pehle group me Voice Chat start karo, "
                "phir /join dobara bhejo."
            )

    except Exception:

        logger.exception(
            "/join failed"
        )

        await message.answer(
            "❌ Zara VC join nahi kar paayi."
        )


# ============================================================
# /END
# ============================================================

@router.message(
    Command("end")
)
async def end_voice_chat(
    message: Message,
) -> None:

    if not message.from_user:
        return

    if not message.chat:
        return

    if not is_group_message(
        message
    ):
        return

    if not await _group_admin(
        message.bot,
        message.chat.id,
        message.from_user.id,
    ):

        await message.answer(
            "⛔ Sirf group admin/owner "
            "Zara ko VC se hata sakta hai."
        )

        return

    try:

        from telegram.client import (
            get_voice_music_services,
        )

        receiver, _ = (
            get_voice_music_services()
        )

        chat_id = message.chat.id

        # ----------------------------------------------------
        # Stop music first
        # ----------------------------------------------------

        try:

            (
                _player,
                _downloader,
                _searcher,
                controls,
            ) = await _music_services()

            await controls.stop(
                chat_id,
                True,
            )

        except Exception:

            logger.debug(
                "Music cleanup during /end failed.",
                exc_info=True,
            )

        # ----------------------------------------------------
        # Leave VC
        # ----------------------------------------------------

        await receiver.leave(
            chat_id
        )

        await message.answer(
            "👋 Zara VC se leave ho gayi "
            "aur music queue clear kar di."
        )

    except Exception:

        logger.exception(
            "/end failed"
        )

        await message.answer(
            "❌ Zara VC se leave nahi kar paayi."
        )


# ============================================================
# /USE
# ============================================================

@router.message(
    Command("use")
)
async def music_use_mode(
    message: Message,
) -> None:

    if not message.from_user:
        return

    if message.from_user.id != OWNER_ID:
        return

    if not message.chat:
        return

    if not is_group_message(
        message
    ):

        await message.answer(
            "/use group me use karo."
        )

        return

    await get_or_create_group(
        message.chat.id,
        title=message.chat.title,
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👥 All User",
                    callback_data=(
                        f"zara_music_mode:"
                        f"all:"
                        f"{message.chat.id}"
                    ),
                ),
                InlineKeyboardButton(
                    text="👑 Admin",
                    callback_data=(
                        f"zara_music_mode:"
                        f"admin:"
                        f"{message.chat.id}"
                    ),
                ),
            ],
        ]
    )

    try:

        from database.groups import (
            get_group_setting,
        )

        mode = await get_group_setting(
            message.chat.id,
            "music_request_mode",
            "admin",
        )

    except Exception:

        mode = "admin"

    await message.answer(
        "🎵 <b>Music Request Mode</b>\n\n"
        f"Current: <b>{str(mode).title()}</b>\n\n"
        "Select who can request songs from VC:",
        reply_markup=keyboard,
    )


# ============================================================
# MUSIC MODE CALLBACK
# ============================================================

@router.callback_query(
    F.data.startswith(
        "zara_music_mode:"
    )
)
async def music_mode_callback(
    callback: CallbackQuery,
) -> None:

    if not callback.from_user:
        return

    if callback.from_user.id != OWNER_ID:

        await callback.answer(
            "Only Zara owner can change this.",
            show_alert=True,
        )

        return

    try:

        if not callback.data:
            await callback.answer(
                "Invalid callback.",
                show_alert=True,
            )
            return

        _, mode, chat_id_raw = (
            callback.data.split(
                ":",
                2,
            )
        )

        chat_id = int(
            chat_id_raw
        )

        from music.voice import (
            MODE_ALL,
            MODE_ADMIN,
        )

        from telegram.client import (
            get_voice_music_services,
        )

        _, controller = (
            get_voice_music_services()
        )

        setter = getattr(
            controller,
            "set_mode",
            None,
        )

        if setter is None:

            await callback.answer(
                "Voice music mode API unavailable.",
                show_alert=True,
            )

            return

        # ----------------------------------------------------
        # Validate mode
        # ----------------------------------------------------

        if mode not in {
            MODE_ALL,
            MODE_ADMIN,
        }:

            await callback.answer(
                "Invalid mode.",
                show_alert=True,
            )

            return

        result = setter(
            chat_id,
            mode,
        )

        if hasattr(
            result,
            "__await__",
        ):

            await result

        label = (
            "All User"
            if mode == MODE_ALL
            else
            "Admin"
        )

        if callback.message:

            await callback.message.edit_text(
                "✅ Music request mode set to "
                f"<b>{label}</b>."
            )

        await callback.answer(
            "Saved"
        )

    except Exception:

        logger.exception(
            "Music mode callback failed"
        )

        await callback.answer(
            "Failed to save mode.",
            show_alert=True,
        )


# ============================================================
# AI MESSAGE HANDLER
# ============================================================

@router.message(
    F.text
)
async def handle_text_message(
    message: Message,
) -> None:

    if not message.from_user:
        return

    text = clean_message_text(
        message
    )

    if not text:
        return

    user_id = (
        message.from_user.id
    )

    # ========================================================
    # ENSURE USER
    # ========================================================

    await ensure_user(
        message
    )

    # ========================================================
    # GROUP DATA
    # ========================================================

    group_settings = None

    if is_group_message(
        message
    ):

        group_settings = (
            await get_group_settings(
                message.chat.id
            )
        )

        # ----------------------------------------------------
        # MUSIC COMMANDS
        #
        # Music commands do NOT require:
        #
        # - @Zara mention
        # - Reply to Zara
        #
        # Examples:
        #
        # play Arijit Singh
        # gana chalao Kesariya
        # pause
        # resume
        # skip
        # stop music
        # queue
        # remove song
        # ----------------------------------------------------

        try:

            intent_result = await detect_intent(
                text
            )

            if is_music_intent(
                intent_result.intent
            ):

                handled = await handle_music_intent(
                    message,
                    intent_result.intent,
                )

                if handled:
                    return

        except Exception:

            logger.exception(
                "Music command handling failed."
            )

        # ----------------------------------------------------
        # Normal AI messages still follow group rules.
        # ----------------------------------------------------

        if not should_answer_group(
            message,
            group_settings,
        ):
            return

    # ========================================================
    # PRIVATE CHAT MUSIC COMMANDS
    # ========================================================

    else:

        try:

            intent_result = await detect_intent(
                text
            )

            if is_music_intent(
                intent_result.intent
            ):

                handled = await handle_music_intent(
                    message,
                    intent_result.intent,
                )

                if handled:
                    return

        except Exception:

            logger.exception(
                "Music command handling failed."
            )

    # ========================================================
    # NORMAL AI MESSAGE
    # ========================================================

    try:

        reply_context = await get_reply_context(
            message
        )

        response = await chat(
            user_id=user_id,
            chat_id=(
                message.chat.id
                if message.chat
                else None
            ),
            text=text,
            reply_context=reply_context,
        )

        if not response:
            return

        await message.answer(
            response
        )

    except Exception:

        logger.exception(
            "Zara AI failed for user %s",
            user_id,
        )

        await message.answer(
            "Sorry, abhi Zara response nahi de pa rahi hai."
        )


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    "router",
    "ensure_user",
    "is_group_message",
    "get_group_settings",
    "bot_is_mentioned",
    "is_reply_to_bot",
    "should_answer_group",
    "get_reply_context",
    "clean_message_text",
    "handle_music_intent",
    "ensure_zara_in_group",
]
