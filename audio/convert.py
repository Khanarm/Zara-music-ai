# audio/convert.py

import asyncio
import logging
from pathlib import Path
from typing import Optional

from audio.ffmpeg import run_ffmpeg


logger = logging.getLogger(__name__)


# ============================================================
# DEFAULT CONFIG
# ============================================================

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1
DEFAULT_CODEC = "pcm_s16le"


# ============================================================
# VALIDATE INPUT
# ============================================================

def validate_input(
    input_path: str | Path,
) -> bool:
    """
    Check whether the input audio file exists.
    """

    path = Path(input_path)

    if not path.exists():
        logger.warning(
            "Audio input does not exist: %s",
            path,
        )
        return False

    if not path.is_file():
        logger.warning(
            "Audio input is not a file: %s",
            path,
        )
        return False

    try:
        if path.stat().st_size <= 0:
            logger.warning(
                "Audio input is empty: %s",
                path,
            )
            return False
    except OSError:
        return False

    return True


# ============================================================
# PREPARE OUTPUT
# ============================================================

def prepare_output(
    output_path: str | Path,
) -> Path:
    """
    Create parent directory for output file.
    """

    path = Path(output_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


# ============================================================
# CONVERT AUDIO
# ============================================================

async def convert_audio(
    input_path: str | Path,
    output_path: str | Path,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    codec: str = DEFAULT_CODEC,
    bitrate: Optional[str] = None,
) -> bool:
    """
    Convert an audio file using FFmpeg.

    Default output:
        WAV
        16 kHz
        Mono
        PCM 16-bit

    This format is suitable for speech-to-text processing.
    """

    input_path = Path(
        input_path
    )

    output_path = prepare_output(
        output_path
    )

    if not validate_input(
        input_path
    ):
        return False

    if sample_rate <= 0:
        raise ValueError(
            "sample_rate must be greater than 0."
        )

    if channels <= 0:
        raise ValueError(
            "channels must be greater than 0."
        )

    command = [
        "-y",
        "-i",
        str(input_path),
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-c:a",
        codec,
    ]

    if bitrate:
        command.extend(
            [
                "-b:a",
                bitrate,
            ]
        )

    command.append(
        str(output_path)
    )

    try:

        return_code = await run_ffmpeg(
            command
        )

        if return_code != 0:

            logger.error(
                "FFmpeg conversion failed: %s",
                input_path,
            )

            return False

        if not output_path.exists():

            logger.error(
                "FFmpeg completed but output file "
                "was not created: %s",
                output_path,
            )

            return False

        if output_path.stat().st_size <= 0:

            logger.error(
                "Converted audio file is empty: %s",
                output_path,
            )

            return False

        logger.debug(
            "Audio converted successfully: %s -> %s",
            input_path,
            output_path,
        )

        return True

    except Exception:

        logger.exception(
            "Audio conversion failed."
        )

        return False


# ============================================================
# TO WAV
# ============================================================

async def to_wav(
    input_path: str | Path,
    output_path: str | Path,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
) -> bool:
    """
    Convert audio to WAV PCM format.
    """

    return await convert_audio(
        input_path=input_path,
        output_path=output_path,
        sample_rate=sample_rate,
        channels=channels,
        codec="pcm_s16le",
    )


# ============================================================
# TO MP3
# ============================================================

async def to_mp3(
    input_path: str | Path,
    output_path: str | Path,
    bitrate: str = "192k",
) -> bool:
    """
    Convert audio to MP3.
    """

    return await convert_audio(
        input_path=input_path,
        output_path=output_path,
        sample_rate=44100,
        channels=2,
        codec="libmp3lame",
        bitrate=bitrate,
    )


# ============================================================
# TO OGG
# ============================================================

async def to_ogg(
    input_path: str | Path,
    output_path: str | Path,
    bitrate: str = "128k",
) -> bool:
    """
    Convert audio to OGG.
    """

    return await convert_audio(
        input_path=input_path,
        output_path=output_path,
        sample_rate=48000,
        channels=2,
        codec="libopus",
        bitrate=bitrate,
    )


# ============================================================
# TO TELEGRAM VOICE
# ============================================================

async def to_telegram_voice(
    input_path: str | Path,
    output_path: str | Path,
) -> bool:
    """
    Convert audio to Telegram-compatible Opus/Ogg voice format.
    """

    input_path = Path(
        input_path
    )

    output_path = prepare_output(
        output_path
    )

    if not validate_input(
        input_path
    ):
        return False

    command = [
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-map_metadata",
        "-1",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-c:a",
        "libopus",
        "-b:a",
        "64k",
        "-application",
        "voip",
        str(output_path),
    ]

    try:

        return_code = await run_ffmpeg(
            command
        )

        if return_code != 0:
            return False

        if not output_path.exists():
            return False

        if output_path.stat().st_size <= 0:
            return False

        return True

    except Exception:

        logger.exception(
            "Failed to create Telegram voice file."
        )

        return False


# ============================================================
# EXTRACT AUDIO FROM VIDEO
# ============================================================

async def extract_audio(
    input_path: str | Path,
    output_path: str | Path,
) -> bool:
    """
    Extract audio from a video/media file.
    """

    input_path = Path(
        input_path
    )

    output_path = prepare_output(
        output_path
    )

    if not validate_input(
        input_path
    ):
        return False

    command = [
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "2",
        "-ar",
        "44100",
        "-c:a",
        "aac",
        str(output_path),
    ]

    try:

        return_code = await run_ffmpeg(
            command
        )

        if return_code != 0:
            return False

        return (
            output_path.exists()
            and output_path.stat().st_size > 0
        )

    except Exception:

        logger.exception(
            "Failed to extract audio."
        )

        return False


# ============================================================
# GET AUDIO DURATION
# ============================================================

async def get_duration(
    input_path: str | Path,
) -> Optional[float]:
    """
    Return audio duration in seconds.

    Uses ffprobe through the FFmpeg helper.
    """

    input_path = Path(
        input_path
    )

    if not validate_input(
        input_path
    ):
        return None

    try:

        from audio.ffmpeg import get_media_info

        info = await get_media_info(
            input_path
        )

        if not info:
            return None

        duration = info.get(
            "duration"
        )

        if duration is None:
            return None

        return float(
            duration
        )

    except Exception:

        logger.exception(
            "Failed to get audio duration."
        )

        return None


# ============================================================
# CHECK CONVERSION
# ============================================================

async def can_convert(
    input_path: str | Path,
) -> bool:
    """
    Check whether FFmpeg can read the input file.
    """

    input_path = Path(
        input_path
    )

    if not validate_input(
        input_path
    ):
        return False

    try:

        from audio.ffmpeg import get_media_info

        info = await get_media_info(
            input_path
        )

        return info is not None

    except Exception:

        logger.exception(
            "Unable to inspect media file."
        )

        return False# Audio conversion helpers
