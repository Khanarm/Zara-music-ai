# telegram/events.py

import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from telegram.client import get_user_client

from ai.brain import chat
from ai.intent import (
    detect_intent,
    is_music_intent,
    MUSIC_PLAY,
    MUSIC_SEARCH,
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

        # Create user if not found.
        user = await create_user(
            user_id=user_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )

        return user

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
    Check whether message came from a group.
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
    Get group configuration from database.
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
    Detect whether Zara was mentioned in the message.
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

        if entity.type == "mention":

            try:
                username = text[
                    entity.offset:
                    entity.offset
                    + entity.length
                ]

                if username.startswith(
                    "@"
                ):
                    return True

            except Exception:
                continue

    return False


def is_reply_to_bot(
    message: Message,
) -> bool:
    """
    Check whether the user replied to Zara.
    """

    if not message.reply_to_message:
        return False

    replied = (
        message.reply_to_message
    )

    if not replied.from_user:
        return False

    # This will be checked against bot identity
    # by the handler when possible.
    return replied.from_user.is_bot


# ============================================================
# GROUP AI PERMISSION
# ============================================================

def should_answer_group(
    message: Message,
    group_settings: Optional[dict],
) -> bool:
    """
    Decide whether Zara should answer in a group.
    """

    # No group configuration yet:
    # allow normal operation.
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

    # Explicit mention.
    if bot_is_mentioned(
        message
    ):
        return True

    # Reply to a bot message.
    if is_reply_to_bot(
        message
    ):
        return True

    return False


# ============================================================
# GET REPLY CONTEXT
# ============================================================

async def get_reply_context(
    message: Message,
) -> Optional[str]:
    """
    Get text of the message being replied to.
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
# CLEAN MENTION
# ============================================================

def clean_message_text(
    message: Message,
) -> str:
    """
    Remove common bot mention from message text.
    """

    text = (
        message.text
        or message.caption
        or ""
    ).strip()

    if not text:
        return ""

    # Remove @username tokens.
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
# MUSIC HANDLER
# ============================================================

async def _music_services():
    from telegram.client import get_music_services
    return get_music_services()

async def handle_music_intent(message: Message, intent: str) -> bool:
    """Handle music intents through the shared music services."""
    if not message.from_user or not message.chat:
        return False
    try:
        player, downloader, searcher, controls = await _music_services()
        chat_id=message.chat.id
        text=clean_message_text(message)
        from ai.intent import MUSIC_PLAY,MUSIC_SEARCH,MUSIC_PAUSE,MUSIC_RESUME,MUSIC_SKIP,MUSIC_STOP,MUSIC_QUEUE,MUSIC_REMOVE

        if intent in (MUSIC_SEARCH, MUSIC_PLAY):
            query=text
            for prefix in ('search song','song search','gana search','gaana search','music search','find song','find music','search music','play','chalao','chala','bajao','baja do','song chala','gana chala','gaana chala'):
                if query.lower().startswith(prefix):
                    query=query[len(prefix):].strip(' :-')
                    break
            if not query:
                current=player.current(chat_id)
                if current and intent==MUSIC_PLAY:
                    ok=await player.play_current(chat_id)
                    await message.answer('▶️ Playing current song.' if ok else '❌ Could not start playback.')
                    return True
                await message.answer('🎵 Song ka naam batao.')
                return True
            result=await searcher.first(query)
            if not result:
                await message.answer('❌ Song nahi mila.')
                return True
            path=await downloader.download(result)
            if not path:
                await message.answer('❌ Song download nahi ho paya. Aaru session/source check karo.')
                return True
            result.metadata['telegram_message']=None
            from music.queue import Track
            track=Track(title=result.title,url=result.url,audio_url=result.audio_url,audio_path=path,duration=result.duration,requested_by=message.from_user.id,requested_by_name=message.from_user.full_name,source=result.source,metadata=result.metadata)
            max_queue=10
            try:
                from config import MUSIC_MAX_QUEUE
                max_queue=int(MUSIC_MAX_QUEUE)
            except Exception: pass
            if player.queue_size(chat_id)>=max_queue:
                await message.answer('⚠️ Queue full hai.')
                return True
            pos=await player.add(chat_id,track,play_now=not player.is_playing(chat_id))
            await message.answer(f'🎵 <b>{result.title}</b>\nQueue position: <b>{pos}</b>')
            return True

        if intent==MUSIC_PAUSE:
            ok=await controls.pause(chat_id); await message.answer('⏸️ Paused.' if ok else '⚠️ Pause is not supported by the current voice engine.'); return True
        if intent==MUSIC_RESUME:
            ok=await controls.resume(chat_id); await message.answer('▶️ Resumed.' if ok else '❌ Nothing to resume.'); return True
        if intent==MUSIC_SKIP:
            ok=await controls.skip(chat_id); await message.answer('⏭️ Skipped.' if ok else '📭 Queue empty hai.'); return True
        if intent==MUSIC_STOP:
            await controls.stop(chat_id,True); await message.answer('⏹️ Music stopped and queue cleared.'); return True
        if intent==MUSIC_QUEUE:
            q=controls.queue(chat_id)
            if not q: await message.answer('📭 Queue empty hai.'); return True
            lines=['🎵 <b>Queue</b>']
            for i,t in enumerate(q,1): lines.append(f'{i}. {t.title}')
            await message.answer('\n'.join(lines[:31])); return True
        if intent==MUSIC_REMOVE:
            q=controls.queue(chat_id)
            if not q: await message.answer('📭 Queue empty hai.'); return True
            removed=controls.remove(chat_id,0)
            await message.answer(f'🗑️ Removed: <b>{removed.title}</b>' if removed else '❌ Song remove nahi hua.')
            return True
    except Exception:
        logger.exception('Music handler failed')
        await message.answer('❌ Music system me error aa gaya.')
        return True
    return False

# ============================================================
# VC MUSIC COMMANDS
# ============================================================

def _is_admin_status(status: str) -> bool:
    return status in {"administrator", "creator", "owner"}


async def _group_admin(bot, chat_id: int, user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return _is_admin_status(str(member.status).lower())
    except Exception:
        return False


@router.message(Command("join"))
async def join_voice_chat(message: Message) -> None:
    if not message.from_user or not message.chat or not is_group_message(message):
        return
    if not await _group_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("⛔ Sirf group admin/owner Zara ko VC me join kara sakta hai.")
        return
    try:
        from telegram.client import get_voice_music_services
        receiver, _ = get_voice_music_services()
        ok = await receiver.join(message.chat.id)
        await message.answer("🎙️ Zara VC me join karke sun rahi hai." if ok else "❌ Active VC nahi mila. Pehle group me Voice Chat start karo.")
    except Exception:
        logger.exception("/join failed")
        await message.answer("❌ Zara VC join nahi kar paayi.")


@router.message(Command("end"))
async def end_voice_chat(message: Message) -> None:
    if not message.from_user or not message.chat or not is_group_message(message):
        return
    if not await _group_admin(message.bot, message.chat.id, message.from_user.id):
        await message.answer("⛔ Sirf group admin/owner Zara ko VC se hata sakta hai.")
        return
    try:
        from telegram.client import get_voice_music_services
        receiver, controller = get_voice_music_services()
        await receiver.leave(message.chat.id)
        await controller.stop(message.chat.id, clear_queue=True)
        await message.answer("👋 Zara VC se leave ho gayi aur music queue clear kar di.")
    except Exception:
        logger.exception("/end failed")
        await message.answer("❌ Zara VC se leave nahi kar paayi.")


@router.message(Command("use"))
async def music_use_mode(message: Message) -> None:
    if not message.from_user or message.from_user.id != OWNER_ID:
        return
    if not message.chat or not is_group_message(message):
        await message.answer("/use group me use karo.")
        return
    await get_or_create_group(message.chat.id, title=message.chat.title)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 All User", callback_data=f"zara_music_mode:all:{message.chat.id}"),
         InlineKeyboardButton(text="👑 Admin", callback_data=f"zara_music_mode:admin:{message.chat.id}")],
    ])
    try:
        from database.groups import get_group_setting
        mode = await get_group_setting(message.chat.id, "music_request_mode", "admin")
    except Exception:
        mode = "admin"
    await message.answer(f"🎵 <b>Music Request Mode</b>\n\nCurrent: <b>{str(mode).title()}</b>\n\nSelect who can request songs from VC:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("zara_music_mode:"))
async def music_mode_callback(callback: CallbackQuery) -> None:
    if not callback.from_user or callback.from_user.id != OWNER_ID:
        await callback.answer("Only Zara owner can change this.", show_alert=True)
        return
    try:
        _, mode, chat_id_raw = callback.data.split(":", 2)
        chat_id = int(chat_id_raw)
        from music.voice import MODE_ALL, MODE_ADMIN
        from telegram.client import get_voice_music_services
        _, controller = get_voice_music_services()
        await controller.set_mode(chat_id, mode)
        label = "All User" if mode == MODE_ALL else "Admin"
        await callback.message.edit_text(f"✅ Music request mode set to <b>{label}</b>.")
        await callback.answer("Saved")
    except Exception:
        logger.exception("Music mode callback failed")
        await callback.answer("Failed to save mode.", show_alert=True)


# ============================================================
# AI MESSAGE HANDLER
# ============================================================

@router.message(
    F.text
)
async def handle_text_message(
    message: Message,
) -> None:
    """
    Main Telegram text message handler.
    """

    if not message.from_user:
        return

    text = clean_message_text(
        message
    )

    if not text:
        return

    user_id = message.from_user.id

    # --------------------------------------------------------
    # Ensure user exists
    # --------------------------------------------------------

    user = await ensure_user(
        message
    )

    # --------------------------------------------------------
    # Group checks
    # --------------------------------------------------------

    group_settings = None

    if is_group_message(
        message
    ):

        group_settings = (
            await get_group_settings(
                message.chat.id
            )
        )

        if not should_answer_group(
            message,
            group_settings,
        ):
            return

    # --------------------------------------------------------
    # Generate Zara response
    # --------------------------------------------------------

    try:

        response = await chat(
            user_id=user_id,
            message=text,
            chat_id=chat_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            is_premium=is_premium,
            group_title=group_title,
            group_language=(
                "Hinglish"
            ),
            ai_enabled=ai_enabled,
            reply_to_all=reply_to_all,
            reply_to_mentions=reply_to_mentions,
            reply_to_message=reply_context,
        )

    except Exception:

        logger.exception(
            "Zara AI failed for user %s",
            user_id,
        )

        try:
            await message.answer(
                "Sorry bhai, abhi thoda technical issue aa gaya. Thodi der baad try karo."
            )
        except Exception:
            pass

        return

    if not response:
        return

    # --------------------------------------------------------
    # Send response
    # --------------------------------------------------------

    try:

        await message.answer(
            response,
            reply_to_message_id=message.message_id,
        )

    except Exception:

        logger.exception(
            "Failed to send Zara response."
        )


# ============================================================
# VOICE MESSAGE HANDLER
# ============================================================

@router.message(
    F.voice
)
async def handle_voice_message(
    message: Message,
) -> None:
    """
    Voice messages will be connected to the STT system.

    Actual processing will be implemented in:
        voice/receiver.py
        voice/processor.py
        voice/stt.py
    """

    if not message.from_user:
        return

    await message.answer(
        "🎙️ Voice processing module abhi connect ho raha hai."
    )


# ============================================================
# AUDIO MESSAGE HANDLER
# ============================================================

@router.message(
    F.audio
)
async def handle_audio_message(
    message: Message,
) -> None:
    """
    Audio messages will be processed by the voice/audio system.
    """

    if not message.from_user:
        return

    await message.answer(
        "🎵 Audio received. Voice-chat playback ke liye ise queue system me add karne ke liye /play use karo."
    )

    await message.answer(
        "🎵 Audio processing module abhi connect ho raha hai."
    )


# ============================================================
# PHOTO / DOCUMENT FALLBACK
# ============================================================

@router.message(
    F.photo
)
async def handle_photo_message(
    message: Message,
) -> None:
    """
    Placeholder for future vision support.
    """

    if not message.from_user:
        return

    caption = (
        message.caption
        or ""
    ).strip()

    if not caption:
        return

    try:

        response = await chat(
            user_id=message.from_user.id,
            message=caption,
            chat_id=message.chat.id,
            username=(
                message.from_user.username
            ),
            first_name=(
                message.from_user.first_name
            ),
            last_name=(
                message.from_user.last_name
            ),
        )

        if response:
            await message.answer(
                response
            )

    except Exception:
        logger.exception(
            "Photo caption processing failed."
        )


# ============================================================
# REGISTER ROUTER
# ============================================================

def register_handlers(
    dispatcher,
) -> None:
    """
    Register Zara event handlers.
    """

    dispatcher.include_router(
        router
    )

    logger.info(
        "Telegram event handlers registered."
)
