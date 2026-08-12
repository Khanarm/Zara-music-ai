# voice/receiver.py

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from aiogram import Bot
from aiogram.types import Message


logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# ============================================================
# TEMP DIRECTORY
# ============================================================

def get_temp_directory() -> Path:
    """
    Create and return Zara's temporary voice directory.
    """

    directory = Path(
        tempfile.gettempdir()
    ) / "zara_ai"

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return directory


# ============================================================
# FILE NAME
# ============================================================

def build_file_path(
    file_id: str,
    extension: str = ".ogg",
) -> Path:
    """
    Build a safe temporary file path.
    """

    safe_file_id = "".join(
        char
        for char in str(file_id)
        if char.isalnum()
        or char in (
            "_",
            "-",
        )
    )

    if not safe_file_id:
        safe_file_id = "voice"

    if not extension.startswith("."):
        extension = "." + extension

    return (
        get_temp_directory()
        / f"{safe_file_id}{extension}"
    )


# ============================================================
# DOWNLOAD TELEGRAM FILE
# ============================================================

async def download_telegram_file(
    bot: Bot,
    file_id: str,
    destination: Path,
    max_size: int = DEFAULT_MAX_FILE_SIZE,
) -> Optional[Path]:
    """
    Download a Telegram file to a temporary path.
    """

    try:

        telegram_file = await bot.get_file(
            file_id
        )

        file_size = getattr(
            telegram_file,
            "file_size",
            None,
        )

        if (
            file_size is not None
            and file_size > max_size
        ):
            logger.warning(
                "Telegram file is too large: %s bytes",
                file_size,
            )

            return None

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        await bot.download_file(
            telegram_file.file_path,
            destination=str(
                destination
            ),
        )

        if not destination.exists():
            logger.error(
                "Telegram file download failed: %s",
                destination,
            )

            return None

        return destination

    except Exception:

        logger.exception(
            "Failed to download Telegram file."
        )

        return None


# ============================================================
# RECEIVE VOICE
# ============================================================

async def receive_voice(
    message: Message,
) -> Optional[Path]:
    """
    Download a Telegram voice message.

    Returns:
        Local temporary file path or None.
    """

    if not message.voice:
        return None

    if not message.bot:
        logger.error(
            "Message does not have an attached bot."
        )

        return None

    file_id = message.voice.file_id

    destination = build_file_path(
        file_id,
        ".ogg",
    )

    return await download_telegram_file(
        bot=message.bot,
        file_id=file_id,
        destination=destination,
    )


# ============================================================
# RECEIVE AUDIO
# ============================================================

async def receive_audio(
    message: Message,
) -> Optional[Path]:
    """
    Download a Telegram audio message.
    """

    if not message.audio:
        return None

    if not message.bot:
        logger.error(
            "Message does not have an attached bot."
        )

        return None

    file_id = message.audio.file_id

    extension = ".mp3"

    if message.audio.file_name:

        suffix = Path(
            message.audio.file_name
        ).suffix.lower()

        if suffix:
            extension = suffix

    destination = build_file_path(
        file_id,
        extension,
    )

    return await download_telegram_file(
        bot=message.bot,
        file_id=file_id,
        destination=destination,
    )


# ============================================================
# RECEIVE DOCUMENT
# ============================================================

async def receive_document(
    message: Message,
) -> Optional[Path]:
    """
    Download an audio/voice document if required.
    """

    if not message.document:
        return None

    if not message.bot:
        return None

    file_id = message.document.file_id

    extension = ".bin"

    if message.document.file_name:

        suffix = Path(
            message.document.file_name
        ).suffix.lower()

        if suffix:
            extension = suffix

    destination = build_file_path(
        file_id,
        extension,
    )

    return await download_telegram_file(
        bot=message.bot,
        file_id=file_id,
        destination=destination,
    )


# ============================================================
# RECEIVE MEDIA
# ============================================================

async def receive_media(
    message: Message,
) -> Optional[Path]:
    """
    Automatically detect voice/audio/document media
    and download it.
    """

    if message.voice:
        return await receive_voice(
            message
        )

    if message.audio:
        return await receive_audio(
            message
        )

    if message.document:
        return await receive_document(
            message
        )

    return None


# ============================================================
# DELETE TEMP FILE
# ============================================================

def delete_temp_file(
    path: Optional[Path],
) -> bool:
    """
    Delete a temporary voice/audio file.
    """

    if not path:
        return False

    try:

        if path.exists():
            path.unlink()

            logger.debug(
                "Temporary voice file deleted: %s",
                path,
            )

            return True

    except Exception:

        logger.exception(
            "Failed to delete temporary file: %s",
            path,
        )

    return False


# ============================================================
# CLEAN TEMP DIRECTORY
# ============================================================

def cleanup_temp_files() -> int:
    """
    Remove temporary Zara voice files.
    """

    directory = get_temp_directory()

    removed = 0

    try:

        for file_path in directory.iterdir():

            if not file_path.is_file():
                continue

            try:
                file_path.unlink()
                removed += 1

            except Exception:
                logger.exception(
                    "Failed to remove temp file: %s",
                    file_path,
                )

    except Exception:

        logger.exception(
            "Failed to clean voice temp directory."
        )

    if removed:
        logger.info(
            "Removed %s temporary voice files.",
            removed,
        )

    return removed
