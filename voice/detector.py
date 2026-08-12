# voice/detector.py

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

DEFAULT_SILENCE_DB = -35
DEFAULT_MIN_SPEECH_SECONDS = 0.20


# ============================================================
# FFPROBE CHECK
# ============================================================

async def _run_ffprobe(
    file_path: Path,
) -> Optional[dict]:
    """
    Get basic audio information using ffprobe.
    """

    if not file_path.exists():
        return None

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=0",
        str(file_path),
    ]

    try:

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.warning(
                "ffprobe failed: %s",
                stderr.decode(
                    errors="ignore"
                ),
            )

            return None

        output = stdout.decode(
            errors="ignore"
        )

        duration = 0.0
        codec = None

        for line in output.splitlines():

            if line.startswith(
                "duration="
            ):

                try:
                    duration = float(
                        line.split(
                            "=",
                            1,
                        )[1]
                    )
                except ValueError:
                    pass

            elif line.startswith(
                "codec_name="
            ):

                codec = line.split(
                    "=",
                    1,
                )[1].strip()

        return {
            "duration": duration,
            "codec": codec,
        }

    except FileNotFoundError:

        logger.error(
            "ffprobe was not found. "
            "Make sure FFmpeg is installed."
        )

        return None

    except Exception:

        logger.exception(
            "Failed to inspect audio."
        )

        return None


# ============================================================
# AUDIO INFO
# ============================================================

async def get_audio_info(
    file_path: Path,
) -> Optional[dict]:
    """
    Return basic information about an audio file.
    """

    return await _run_ffprobe(
        file_path
    )


# ============================================================
# DURATION CHECK
# ============================================================

async def has_audio(
    file_path: Path,
) -> bool:
    """
    Check whether the file contains usable audio.
    """

    info = await get_audio_info(
        file_path
    )

    if not info:
        return False

    return info.get(
        "duration",
        0.0,
    ) > 0


# ============================================================
# SILENCE DETECTION
# ============================================================

async def detect_speech(
    file_path: Path,
    silence_db: int = DEFAULT_SILENCE_DB,
    min_speech_seconds: float = DEFAULT_MIN_SPEECH_SECONDS,
) -> bool:
    """
    Detect whether an audio file contains speech/audio
    rather than being completely silent.

    This uses FFmpeg's silencedetect filter.

    It is intentionally conservative: the goal is to avoid
    sending completely empty audio to STT.
    """

    if not file_path.exists():
        return False

    command = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        str(file_path),
        "-af",
        (
            f"silencedetect="
            f"noise={silence_db}dB:"
            f"d={min_speech_seconds}"
        ),
        "-f",
        "null",
        "-",
    ]

    try:

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        _, stderr = await process.communicate()

        output = stderr.decode(
            errors="ignore"
        )

        if process.returncode != 0:

            logger.warning(
                "FFmpeg speech detection failed."
            )

            return False

        # ----------------------------------------------------
        # If FFmpeg reports silence_start and silence_end
        # covering the entire file, treat it as silence.
        # ----------------------------------------------------

        info = await get_audio_info(
            file_path
        )

        if not info:
            return False

        duration = float(
            info.get(
                "duration",
                0.0,
            )
        )

        if duration <= 0:
            return False

        silence_start = None
        silence_end = None

        for line in output.splitlines():

            if "silence_start:" in line:

                try:
                    value = line.split(
                        "silence_start:",
                        1,
                    )[1].strip()

                    silence_start = float(
                        value.split()[0]
                    )

                except (ValueError, IndexError):
                    pass

            if "silence_end:" in line:

                try:
                    value = line.split(
                        "silence_end:",
                        1,
                    )[1].strip()

                    silence_end = float(
                        value.split()[0]
                    )

                except (ValueError, IndexError):
                    pass

        # Completely silent file.
        if (
            silence_start is not None
            and silence_start <= 0.1
            and silence_end is not None
            and silence_end >= duration - 0.1
        ):
            return False

        return True

    except FileNotFoundError:

        logger.error(
            "FFmpeg was not found. "
            "Install FFmpeg before using voice detection."
        )

        return False

    except Exception:

        logger.exception(
            "Speech detection failed."
        )

        return False


# ============================================================
# QUICK SPEECH CHECK
# ============================================================

async def is_speech(
    file_path: Path,
) -> bool:
    """
    Simple public speech check.
    """

    if not file_path:
        return False

    if not file_path.exists():
        return False

    return await detect_speech(
        file_path
    )


# ============================================================
# VALIDATE SPEECH FILE
# ============================================================

async def validate_speech(
    file_path: Path,
    min_duration: float = 0.20,
    max_duration: float = 300.0,
) -> bool:
    """
    Validate that an audio file is suitable for STT.
    """

    if not file_path:
        return False

    if not file_path.exists():
        return False

    info = await get_audio_info(
        file_path
    )

    if not info:
        return False

    duration = float(
        info.get(
            "duration",
            0.0,
        )
    )

    if duration < min_duration:
        logger.debug(
            "Audio is too short: %.2f seconds",
            duration,
        )

        return False

    if duration > max_duration:
        logger.warning(
            "Audio is too long: %.2f seconds",
            duration,
        )

        return False

    return await detect_speech(
        file_path
    )


# ============================================================
# DETECTOR CLASS
# ============================================================

class SpeechDetector:
    """
    Reusable speech detector.
    """

    def __init__(
        self,
        silence_db: int = DEFAULT_SILENCE_DB,
        min_speech_seconds: float = DEFAULT_MIN_SPEECH_SECONDS,
    ):
        self.silence_db = silence_db
        self.min_speech_seconds = (
            min_speech_seconds
        )

    async def detect(
        self,
        file_path: Path,
    ) -> bool:

        return await detect_speech(
            file_path=file_path,
            silence_db=self.silence_db,
            min_speech_seconds=(
                self.min_speech_seconds
            ),
        )

    async def validate(
        self,
        file_path: Path,
    ) -> bool:

        return await validate_speech(
            file_path
        )


# ============================================================
# DEFAULT DETECTOR
# ============================================================

detector = SpeechDetector()
