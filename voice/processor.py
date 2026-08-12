# voice/processor.py

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from audio.convert import convert_audio


logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

MAX_AUDIO_SIZE = 50 * 1024 * 1024  # 50 MB

SUPPORTED_INPUT_EXTENSIONS = {
    ".ogg",
    ".oga",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".opus",
    ".webm",
    ".flac",
}

OUTPUT_EXTENSION = ".wav"


# ============================================================
# TEMP DIRECTORY
# ============================================================

def get_processing_directory() -> Path:
    """
    Return Zara's temporary audio-processing directory.
    """

    directory = (
        Path(tempfile.gettempdir())
        / "zara_ai"
        / "processed"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return directory


# ============================================================
# VALIDATE FILE
# ============================================================

def validate_audio_file(
    file_path: Path,
) -> bool:
    """
    Validate an audio file before processing.
    """

    if not file_path:
        return False

    if not file_path.exists():
        logger.warning(
            "Audio file does not exist: %s",
            file_path,
        )

        return False

    if not file_path.is_file():
        logger.warning(
            "Audio path is not a file: %s",
            file_path,
        )

        return False

    try:
        file_size = file_path.stat().st_size

        if file_size <= 0:
            logger.warning(
                "Audio file is empty: %s",
                file_path,
            )

            return False

        if file_size > MAX_AUDIO_SIZE:
            logger.warning(
                "Audio file is too large: %s bytes",
                file_size,
            )

            return False

    except OSError:

        logger.exception(
            "Failed to inspect audio file."
        )

        return False

    extension = (
        file_path.suffix.lower()
    )

    if extension not in SUPPORTED_INPUT_EXTENSIONS:
        logger.warning(
            "Unsupported audio extension: %s",
            extension,
        )

        return False

    return True


# ============================================================
# OUTPUT PATH
# ============================================================

def build_output_path(
    source: Path,
) -> Path:
    """
    Build a unique WAV output path.
    """

    import uuid

    filename = (
        f"{source.stem}_"
        f"{uuid.uuid4().hex}"
        f"{OUTPUT_EXTENSION}"
    )

    return (
        get_processing_directory()
        / filename
    )


# ============================================================
# PROCESS AUDIO
# ============================================================

async def process_audio(
    file_path: Path,
) -> Optional[Path]:
    """
    Convert incoming audio into a standard WAV file
    suitable for speech-to-text processing.

    Returns:
        Processed WAV path or None.
    """

    if not validate_audio_file(
        file_path
    ):
        return None

    output_path = build_output_path(
        file_path
    )

    try:

        result = await convert_audio(
            input_path=str(
                file_path
            ),
            output_path=str(
                output_path
            ),
            sample_rate=16000,
            channels=1,
            codec="pcm_s16le",
        )

        if result is False:
            logger.error(
                "Audio conversion failed."
            )

            return None

        if not output_path.exists():
            logger.error(
                "Audio converter did not create output file."
            )

            return None

        if output_path.stat().st_size <= 0:
            logger.error(
                "Processed audio file is empty."
            )

            try:
                output_path.unlink()
            except OSError:
                pass

            return None

        logger.debug(
            "Audio processed successfully: %s",
            output_path,
        )

        return output_path

    except Exception:

        logger.exception(
            "Failed to process audio."
        )

        try:
            if output_path.exists():
                output_path.unlink()
        except OSError:
            pass

        return None


# ============================================================
# PROCESS TELEGRAM VOICE
# ============================================================

async def process_voice(
    file_path: Path,
) -> Optional[Path]:
    """
    Process a Telegram voice file.
    """

    return await process_audio(
        file_path
    )


# ============================================================
# PROCESS TELEGRAM AUDIO
# ============================================================

async def process_audio_message(
    file_path: Path,
) -> Optional[Path]:
    """
    Process a Telegram audio file.
    """

    return await process_audio(
        file_path
    )


# ============================================================
# AUDIO INFORMATION
# ============================================================

def get_audio_info(
    file_path: Path,
) -> dict:
    """
    Return basic local file information.
    """

    if not file_path:
        return {
            "exists": False,
        }

    try:

        if not file_path.exists():
            return {
                "exists": False,
                "path": str(file_path),
            }

        stat = file_path.stat()

        return {
            "exists": True,
            "path": str(file_path),
            "name": file_path.name,
            "extension": file_path.suffix.lower(),
            "size": stat.st_size,
        }

    except Exception:

        logger.exception(
            "Failed to get audio information."
        )

        return {
            "exists": False,
            "path": str(file_path),
        }


# ============================================================
# DELETE PROCESSED FILE
# ============================================================

def delete_processed_file(
    file_path: Optional[Path],
) -> bool:
    """
    Delete a processed temporary audio file.
    """

    if not file_path:
        return False

    try:

        if file_path.exists():
            file_path.unlink()

            logger.debug(
                "Processed audio deleted: %s",
                file_path,
            )

            return True

    except Exception:

        logger.exception(
            "Failed to delete processed audio."
        )

    return False


# ============================================================
# CLEAN PROCESSING DIRECTORY
# ============================================================

def cleanup_processed_files() -> int:
    """
    Remove all temporary processed audio files.
    """

    directory = (
        get_processing_directory()
    )

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
                    "Failed to remove processed file: %s",
                    file_path,
                )

    except Exception:

        logger.exception(
            "Failed to clean processing directory."
        )

    if removed:
        logger.info(
            "Removed %s processed audio files.",
            removed,
        )

    return removed
