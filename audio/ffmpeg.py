# audio/ffmpeg.py

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

FFMPEG_BINARY = os.getenv(
    "FFMPEG_BINARY",
    "ffmpeg",
)

FFPROBE_BINARY = os.getenv(
    "FFPROBE_BINARY",
    "ffprobe",
)

FFMPEG_TIMEOUT = int(
    os.getenv(
        "FFMPEG_TIMEOUT",
        "120",
    )
)


# ============================================================
# BINARY CHECK
# ============================================================

def is_ffmpeg_available() -> bool:
    """
    Check whether FFmpeg is installed.
    """

    return shutil.which(
        FFMPEG_BINARY
    ) is not None


def is_ffprobe_available() -> bool:
    """
    Check whether FFprobe is installed.
    """

    return shutil.which(
        FFPROBE_BINARY
    ) is not None


def check_ffmpeg() -> bool:
    """
    Check FFmpeg and FFprobe availability.
    """

    return (
        is_ffmpeg_available()
        and is_ffprobe_available()
    )


# ============================================================
# RUN FFMPEG
# ============================================================

async def run_ffmpeg(
    arguments: list[str],
    timeout: Optional[int] = None,
) -> int:
    """
    Execute FFmpeg asynchronously.

    Returns:
        FFmpeg process return code.
    """

    if not is_ffmpeg_available():

        logger.error(
            "FFmpeg binary not found: %s",
            FFMPEG_BINARY,
        )

        return -1

    if not arguments:
        raise ValueError(
            "FFmpeg arguments cannot be empty."
        )

    command = [
        FFMPEG_BINARY,
        *arguments,
    ]

    logger.debug(
        "Running FFmpeg: %s",
        " ".join(command),
    )

    process = None

    try:

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=(
                timeout
                or FFMPEG_TIMEOUT
            ),
        )

        if stdout:
            logger.debug(
                "FFmpeg stdout: %s",
                stdout.decode(
                    errors="ignore"
                )[-2000:],
            )

        if stderr:

            error_output = stderr.decode(
                errors="ignore"
            )

            if process.returncode != 0:
                logger.error(
                    "FFmpeg error: %s",
                    error_output[-4000:],
                )
            else:
                logger.debug(
                    "FFmpeg output: %s",
                    error_output[-2000:],
                )

        return process.returncode

    except asyncio.TimeoutError:

        logger.error(
            "FFmpeg process timed out."
        )

        if process is not None:

            try:
                process.kill()
                await process.wait()
            except Exception:
                pass

        return -2

    except FileNotFoundError:

        logger.error(
            "FFmpeg executable not found."
        )

        return -1

    except Exception:

        logger.exception(
            "Unexpected FFmpeg error."
        )

        return -3


# ============================================================
# RUN FFPROBE
# ============================================================

async def run_ffprobe(
    arguments: list[str],
    timeout: Optional[int] = None,
) -> Optional[str]:
    """
    Execute FFprobe asynchronously.

    Returns:
        stdout text or None on failure.
    """

    if not is_ffprobe_available():

        logger.error(
            "FFprobe binary not found: %s",
            FFPROBE_BINARY,
        )

        return None

    if not arguments:
        raise ValueError(
            "FFprobe arguments cannot be empty."
        )

    command = [
        FFPROBE_BINARY,
        *arguments,
    ]

    try:

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=(
                timeout
                or FFMPEG_TIMEOUT
            ),
        )

        if process.returncode != 0:

            logger.warning(
                "FFprobe failed: %s",
                stderr.decode(
                    errors="ignore"
                )[-3000:],
            )

            return None

        return stdout.decode(
            errors="ignore"
        )

    except asyncio.TimeoutError:

        logger.error(
            "FFprobe process timed out."
        )

        try:
            process.kill()
            await process.wait()
        except Exception:
            pass

        return None

    except FileNotFoundError:

        logger.error(
            "FFprobe executable not found."
        )

        return None

    except Exception:

        logger.exception(
            "Unexpected FFprobe error."
        )

        return None


# ============================================================
# MEDIA INFORMATION
# ============================================================

async def get_media_info(
    file_path: str | Path,
) -> Optional[dict]:
    """
    Return detailed media information using FFprobe.
    """

    path = Path(
        file_path
    )

    if not path.exists():
        logger.warning(
            "Media file does not exist: %s",
            path,
        )

        return None

    if not path.is_file():
        return None

    arguments = [
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    output = await run_ffprobe(
        arguments
    )

    if not output:
        return None

    try:

        return json.loads(
            output
        )

    except json.JSONDecodeError:

        logger.exception(
            "Failed to parse FFprobe JSON."
        )

        return None


# ============================================================
# AUDIO INFORMATION
# ============================================================

async def get_audio_info(
    file_path: str | Path,
) -> Optional[dict]:
    """
    Return useful information about the first audio stream.
    """

    info = await get_media_info(
        file_path
    )

    if not info:
        return None

    streams = info.get(
        "streams",
        [],
    )

    audio_stream = None

    for stream in streams:

        if stream.get(
            "codec_type"
        ) == "audio":

            audio_stream = stream
            break

    if audio_stream is None:
        return None

    format_info = info.get(
        "format",
        {},
    )

    duration = (
        audio_stream.get(
            "duration"
        )
        or format_info.get(
            "duration"
        )
    )

    try:
        duration = (
            float(duration)
            if duration is not None
            else None
        )
    except (TypeError, ValueError):
        duration = None

    sample_rate = audio_stream.get(
        "sample_rate"
    )

    try:
        sample_rate = (
            int(sample_rate)
            if sample_rate is not None
            else None
        )
    except (TypeError, ValueError):
        sample_rate = None

    channels = audio_stream.get(
        "channels"
    )

    try:
        channels = (
            int(channels)
            if channels is not None
            else None
        )
    except (TypeError, ValueError):
        channels = None

    return {
        "codec": audio_stream.get(
            "codec_name"
        ),
        "codec_long_name": audio_stream.get(
            "codec_long_name"
        ),
        "duration": duration,
        "sample_rate": sample_rate,
        "channels": channels,
        "channel_layout": audio_stream.get(
            "channel_layout"
        ),
        "bit_rate": audio_stream.get(
            "bit_rate"
        ),
        "format": format_info.get(
            "format_name"
        ),
        "filename": format_info.get(
            "filename"
        ),
    }


# ============================================================
# VIDEO INFORMATION
# ============================================================

async def get_video_info(
    file_path: str | Path,
) -> Optional[dict]:
    """
    Return information about the first video stream.
    """

    info = await get_media_info(
        file_path
    )

    if not info:
        return None

    streams = info.get(
        "streams",
        [],
    )

    for stream in streams:

        if stream.get(
            "codec_type"
        ) != "video":
            continue

        return {
            "codec": stream.get(
                "codec_name"
            ),
            "width": stream.get(
                "width"
            ),
            "height": stream.get(
                "height"
            ),
            "duration": stream.get(
                "duration"
            ),
            "fps": stream.get(
                "r_frame_rate"
            ),
            "pixel_format": stream.get(
                "pix_fmt"
            ),
        }

    return None


# ============================================================
# DURATION
# ============================================================

async def get_duration(
    file_path: str | Path,
) -> Optional[float]:
    """
    Return media duration in seconds.
    """

    info = await get_media_info(
        file_path
    )

    if not info:
        return None

    format_info = info.get(
        "format",
        {},
    )

    duration = format_info.get(
        "duration"
    )

    if duration is None:

        for stream in info.get(
            "streams",
            [],
        ):

            if stream.get(
                "duration"
            ) is not None:

                duration = stream.get(
                    "duration"
                )

                break

    try:

        return float(
            duration
        ) if duration is not None else None

    except (
        TypeError,
        ValueError,
    ):

        return None


# ============================================================
# CONVERT USING RAW ARGUMENTS
# ============================================================

async def convert_with_ffmpeg(
    input_path: str | Path,
    output_path: str | Path,
    extra_arguments: Optional[list[str]] = None,
) -> bool:
    """
    Generic FFmpeg conversion helper.
    """

    input_path = Path(
        input_path
    )

    output_path = Path(
        output_path
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    arguments = [
        "-y",
        "-i",
        str(input_path),
    ]

    if extra_arguments:
        arguments.extend(
            extra_arguments
        )

    arguments.append(
        str(output_path)
    )

    return_code = await run_ffmpeg(
        arguments
    )

    if return_code != 0:
        return False

    return (
        output_path.exists()
        and output_path.stat().st_size > 0
    )


# ============================================================
# VERSION
# ============================================================

async def get_ffmpeg_version() -> Optional[str]:
    """
    Return installed FFmpeg version.
    """

    if not is_ffmpeg_available():
        return None

    try:

        process = await asyncio.create_subprocess_exec(
            FFMPEG_BINARY,
            "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, _ = await process.communicate()

        if process.returncode != 0:
            return None

        first_line = (
            stdout.decode(
                errors="ignore"
            )
            .splitlines()
        )

        if first_line:
            return first_line[0].strip()

    except Exception:

        logger.exception(
            "Failed to get FFmpeg version."
        )

    return None
