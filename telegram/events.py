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
        if intent in {MUSIC_SEARCH, MUSIC_PLAY, MUSIC_VIDEO}:
            query = text

            prefixes = (
                "search song", "song search", "gana search", "gaana search",
                "music search", "find song", "find music", "search music",
                "play song", "play music", "play", "chalao", "chala",
                "bajao", "baja do", "song chala", "gana chala",
                "gaana chala", "video chalao", "video bajao", "video play",
                "video dikhao",
            )

            lowered = query.lower()
            for prefix in prefixes:
                if lowered.startswith(prefix):
                    query = query[len(prefix):].strip(" :-")
                    break

            if not query:
                current = player.current(chat_id)
                if current and intent == MUSIC_PLAY:
                    ok = await player.play_current(chat_id)
                    if processing:
                        try: await processing.delete()
                        except Exception: pass
                    await message.bot.send_message(
                        chat_id,
                        "▶️ Playing current song." if ok else "❌ Could not start playback.",
                    )
                    return True

                if processing:
                    try: await processing.delete()
                    except Exception: pass
                await message.bot.send_message(chat_id, "🎵 Song ka naam batao.")
                return True

            try:
                max_queue = int(MUSIC_MAX_QUEUE)
            except Exception:
                max_queue = 10

            # Start VC join and YouTube search at the same time.
            join_task = None
            try:
                from telegram.client import get_voice_music_services
                receiver, _controller = get_voice_music_services()
                join_task = asyncio.create_task(receiver.join(chat_id))
            except Exception:
                logger.debug("VC join task could not be started.", exc_info=True)

            if player.queue_size(chat_id) >= max_queue:
                if join_task:
                    join_task.cancel()
                if processing:
                    try: await processing.delete()
                    except Exception: pass
                await message.bot.send_message(chat_id, "⚠️ Queue full hai.")
                return True

            try:
                result = await searcher.first(query)
            except Exception:
                logger.exception("Music search failed: %s", query)
                if join_task:
                    join_task.cancel()
                if processing:
                    try: await processing.delete()
                    except Exception: pass
                await message.bot.send_message(chat_id, "❌ Song search me error aa gaya.")
                return True

            if not result:
                if join_task:
                    join_task.cancel()
                if processing:
                    try: await processing.delete()
                    except Exception: pass
                await message.bot.send_message(chat_id, f"❌ <b>{query}</b> nahi mila.")
                return True

            is_video = intent == MUSIC_VIDEO

            try:
                if is_video:
                    try:
                        path = await downloader.download(result, video=True)
                    except TypeError:
                        path = await downloader.download(result)
                else:
                    path = await downloader.download(result)
            except Exception:
                logger.exception("Music download failed: %s", result.title)
                if join_task:
                    join_task.cancel()
                if processing:
                    try: await processing.delete()
                    except Exception: pass
                await message.bot.send_message(chat_id, "❌ Song download nahi ho paya.")
                return True

            if not path:
                if join_task:
                    join_task.cancel()
                if processing:
                    try: await processing.delete()
                    except Exception: pass
                await message.bot.send_message(chat_id, "❌ Song/media download nahi ho paya.")
                return True

            from music.queue import Track
            metadata = dict(getattr(result, "metadata", {}) or {})
            metadata["telegram_message"] = None

            track = Track(
                title=result.title,
                url=result.url,
                audio_url=result.url,
                audio_path=path,
                duration=result.duration,
                requested_by=user_id,
                requested_by_name=message.from_user.full_name,
                thumbnail=getattr(result, "thumbnail", None),
                source=getattr(result, "source", None),
                media_type="video" if is_video else "audio",
                metadata=metadata,
            )

            # Wait only for the VC join after search/download work is ready.
            if join_task:
                try:
                    joined = await join_task
                except Exception:
                    joined = False
                if not joined:
                    try:
                        await downloader.delete(path)
                    except Exception:
                        logger.debug("Failed to cleanup downloaded file after VC join failure.", exc_info=True)
                    if processing:
                        try: await processing.delete()
                        except Exception: pass
                    await message.bot.send_message(
                        chat_id,
                        "❌ Zara VC me join nahi kar paayi.",
                    )
                    return True

            was_playing = player.is_playing(chat_id)
            position = await player.add(
                chat_id,
                track,
                play_now=not was_playing,
            )

            if not was_playing and (
                player.current(chat_id) is None
                or not player.is_playing(chat_id)
            ):
                if processing:
                    try: await processing.delete()
                    except Exception: pass
                try:
                    await downloader.delete(path)
                except Exception:
                    logger.debug("Failed to cleanup downloaded file after playback failure.", exc_info=True)
                await message.bot.send_message(
                    chat_id,
                    "❌ Song ready tha, lekin VC playback start nahi hua.",
                )
                return True

            if processing:
                try: await processing.delete()
                except Exception: pass

            if was_playing:
                await message.bot.send_message(
                    chat_id,
                    f"🎵 <b>{result.title}</b>\n"
                    f"🎵 Play by Zara Music\n"
                    f"👤 Requested by: <b>{message.from_user.full_name}</b>\n"
                    f"⏭️ Queue position: <b>{position}</b>",
                )
            else:
                await message.bot.send_message(
                    chat_id,
                    f"🎵 <b>{result.title}</b>\n"
                    f"🎵 Play by Zara Music\n"
                    f"👤 Requested by: <b>{message.from_user.full_name}</b>",
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

            result_type, track = await player.skip_for_user(
                chat_id,
                user_id,
                admin=is_admin,
            )

            if processing:
                try: await processing.delete()
                except Exception: pass

            if result_type == "current":
                current = player.current(chat_id)
                if current:
                    text_out = (
                        f"⏭️ <b>{track.title}</b> skipped.\n"
                        f"▶️ Next: <b>{current.title}</b>"
                    )
                else:
                    text_out = f"⏭️ <b>{track.title}</b> skipped.\n📭 Queue empty hai."
            elif result_type == "queue":
                text_out = f"⏭️ Tumhara queued song <b>{track.title}</b> skip kar diya."
            else:
                text_out = "⛔ Tum current song ke requester nahi ho aur tumhara koi queued song nahi hai."

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
]
