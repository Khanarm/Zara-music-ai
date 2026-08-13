# telegram/events.py

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

from config import OWNER_ID


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
    """
    Handle text-based music commands.
    """

    if not message.from_user:
        return False

    if not message.chat:
        return False

    try:

        (
            player,
            downloader,
            searcher,
            controls,
        ) = await _music_services()

        chat_id = message.chat.id

        text = clean_message_text(
            message
        )

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

                if lowered.startswith(
                    prefix
                ):

                    query = query[
                        len(prefix):
                    ].strip(
                        " :-"
                    )

                    break

            # ------------------------------------------------
            # No query
            # ------------------------------------------------

            if not query:

                current = player.current(
                    chat_id
                )

                if (
                    current
                    and intent == MUSIC_PLAY
                ):

                    play_current = getattr(
                        player,
                        "play_current",
                        None,
                    )

                    if play_current is None:

                        await message.answer(
                            "❌ Current song ko play karne ka option available nahi hai."
                        )

                        return True

                    result = play_current(
                        chat_id
                    )

                    if hasattr(
                        result,
                        "__await__",
                    ):
                        ok = await result
                    else:
                        ok = bool(result)

                    await message.answer(
                        "▶️ Playing current song."
                        if ok
                        else
                        "❌ Could not start playback."
                    )

                    return True

                await message.answer(
                    "🎵 Song ka naam batao."
                )

                return True

            # ------------------------------------------------
            # Queue limit
            # ------------------------------------------------

            try:
                from config import (
                    MUSIC_MAX_QUEUE,
                )

                max_queue = int(
                    MUSIC_MAX_QUEUE
                )

            except Exception:
                max_queue = 10

            if player.queue_size(
                chat_id
            ) >= max_queue:

                await message.answer(
                    "⚠️ Queue full hai."
                )

                return True

            # ------------------------------------------------
            # SEARCH
            # ------------------------------------------------

            result = await searcher.first(
                query
            )

            if not result:

                await message.answer(
                    f"❌ <b>{query}</b> nahi mila."
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

                        logger.warning(
                            "Downloader does not support video=True. "
                            "Falling back to normal download."
                        )

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

                await message.answer(
                    "❌ Song download nahi ho paya."
                )

                return True

            if not path:

                await message.answer(
                    "❌ Song/media download nahi ho paya."
                )

                return True

            # ------------------------------------------------
            # TRACK
            # ------------------------------------------------

            try:
                result.metadata[
                    "telegram_message"
                ] = None

            except Exception:
                pass

            from music.queue import Track

            metadata = {}

            try:
                metadata.update(
                    result.metadata or {}
                )
            except Exception:
                pass

            track = Track(
                title=result.title,
                url=result.url,
                audio_url=result.url,
                audio_path=path,
                duration=result.duration,
                requested_by=message.from_user.id,
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
            # PLAY / QUEUE
            # ------------------------------------------------

            was_playing = player.is_playing(
                chat_id
            )

            position = await player.add(
                chat_id,
                track,
                play_now=not was_playing,
            )

            if not was_playing:

                await message.answer(
                    f"🎵 <b>{result.title}</b>\n"
                    "▶️ Abhi play ho raha hai."
                )

            else:

                await message.answer(
                    f"🎵 <b>{result.title}</b>\n"
                    f"⏭️ Queue position: <b>{position}</b>"
                )

            return True

        # ====================================================
        # PAUSE
        # ====================================================

        if intent == MUSIC_PAUSE:

            ok = await controls.pause(
                chat_id
            )

            await message.answer(
                "⏸️ Paused."
                if ok
                else
                "⚠️ Pause is not supported."
            )

            return True

        # ====================================================
        # RESUME
        # ====================================================

        if intent == MUSIC_RESUME:

            ok = await controls.resume(
                chat_id
            )

            await message.answer(
                "▶️ Resumed."
                if ok
                else
                "❌ Nothing to resume."
            )

            return True

        # ====================================================
        # SKIP
        # ====================================================

        if intent == MUSIC_SKIP:

            ok = await controls.skip(
                chat_id
            )

            await message.answer(
                "⏭️ Skipped."
                if ok
                else
                "📭 Queue empty hai."
            )

            return True

        # ====================================================
        # STOP
        # ====================================================

        if intent == MUSIC_STOP:

            await controls.stop(
                chat_id,
                True,
            )

            await message.answer(
                "⏹️ Music stopped and queue cleared."
            )

            return True

        # ====================================================
        # QUEUE
        # ====================================================

        if intent == MUSIC_QUEUE:

            q = controls.queue(
                chat_id
            )

            current = None

            try:
                current = player.current(
                    chat_id
                )
            except Exception:
                pass

            if not q and not current:

                await message.answer(
                    "📭 Queue empty hai."
                )

                return True

            lines = [
                "🎵 <b>Zara Music Queue</b>"
            ]

            if current:

                lines.append(
                    f"▶️ Now: <b>{current.title}</b>"
                )

            for i, track in enumerate(
                q,
                1,
            ):

                lines.append(
                    f"{i}. {track.title}"
                )

            await message.answer(
                "\n".join(
                    lines[:31]
                )
            )

            return True

        # ====================================================
        # REMOVE
        # ====================================================

        if intent == MUSIC_REMOVE:

            q = controls.queue(
                chat_id
            )

            if not q:

                await message.answer(
                    "📭 Queue empty hai."
                )

                return True

            removed = controls.remove(
                chat_id,
                0,
            )

            await message.answer(
                (
                    f"🗑️ Removed: "
                    f"<b>{removed.title}</b>"
                )
                if removed
                else
                "❌ Song remove nahi hua."
            )

            return True

    except Exception:

        logger.exception(
            "Music handler failed"
        )

        await message.answer(
            "❌ Music system me error aa gaya."
        )

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
