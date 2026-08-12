# voice/tts.py

import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

TTS_PROVIDER = os.getenv(
    "TTS_PROVIDER",
    "system",
).lower().strip()

TTS_LANGUAGE = os.getenv(
    "TTS_LANGUAGE",
    "hi",
)

TTS_TIMEOUT = int(
    os.getenv(
        "TTS_TIMEOUT",
        "60",
    )
)

TTS_VOICE = os.getenv(
    "TTS_VOICE",
    "",
).strip()


# ============================================================
# RESULT
# ============================================================

class TTSResult:
    """
    Text-to-speech result.
    """

    def __init__(
        self,
        audio_path: Optional[Path] = None,
        text: str = "",
        success: bool = False,
    ):
        self.audio_path = audio_path
        self.text = text
        self.success = success

    def __bool__(self) -> bool:
        return self.success and bool(
            self.audio_path
        )

    def to_dict(self) -> dict:
        return {
            "audio_path": (
                str(self.audio_path)
                if self.audio_path
                else None
            ),
            "text": self.text,
            "success": self.success,
        }


# ============================================================
# TEMP DIRECTORY
# ============================================================

def get_tts_directory() -> Path:
    """
    Return temporary TTS directory.
    """

    import tempfile

    directory = (
        Path(tempfile.gettempdir())
        / "zara_ai"
        / "tts"
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    return directory


# ============================================================
# OUTPUT PATH
# ============================================================

def build_output_path(
    extension: str = ".wav",
) -> Path:
    """
    Create a unique TTS output path.
    """

    import uuid

    if not extension.startswith("."):
        extension = "." + extension

    filename = (
        f"tts_"
        f"{uuid.uuid4().hex}"
        f"{extension}"
    )

    return (
        get_tts_directory()
        / filename
    )


# ============================================================
# TEXT VALIDATION
# ============================================================

def validate_text(
    text: str,
    max_length: int = 5000,
) -> bool:
    """
    Validate text before TTS generation.
    """

    if not text:
        return False

    text = str(
        text
    ).strip()

    if not text:
        return False

    if len(text) > max_length:
        logger.warning(
            "TTS text is too long: %s characters",
            len(text),
        )

        return False

    return True


# ============================================================
# SYSTEM TTS
# ============================================================

async def synthesize_with_system(
    text: str,
    output_path: Path,
    language: Optional[str] = None,
) -> Optional[Path]:
    """
    Generate speech using a locally available TTS command.

    Supported commands:
    - edge-tts
    - espeak
    - espeak-ng

    The first available command is used.
    """

    if not validate_text(
        text
    ):
        return None

    language = (
        language
        or TTS_LANGUAGE
    )

    # --------------------------------------------------------
    # edge-tts
    # --------------------------------------------------------

    try:

        edge_voice = (
            TTS_VOICE
            or (
                "hi-IN-SwaraNeural"
                if language.startswith("hi")
                else "en-US-AriaNeural"
            )
        )

        command = [
            "edge-tts",
            "--voice",
            edge_voice,
            "--text",
            text,
            "--write-media",
            str(output_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        _, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=TTS_TIMEOUT,
        )

        if (
            process.returncode == 0
            and output_path.exists()
            and output_path.stat().st_size > 0
        ):
            return output_path

        logger.debug(
            "edge-tts unavailable or failed: %s",
            stderr.decode(
                errors="ignore"
            ),
        )

    except FileNotFoundError:
        logger.debug(
            "edge-tts is not installed."
        )

    except asyncio.TimeoutError:
        logger.warning(
            "edge-tts timed out."
        )

    except Exception:
        logger.exception(
            "edge-tts failed."
        )

    # --------------------------------------------------------
    # espeak-ng / espeak
    # --------------------------------------------------------

    for executable in (
        "espeak-ng",
        "espeak",
    ):

        try:

            command = [
                executable,
                "-w",
                str(output_path),
                text,
            ]

            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            _, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=TTS_TIMEOUT,
            )

            if (
                process.returncode == 0
                and output_path.exists()
                and output_path.stat().st_size > 0
            ):
                return output_path

            logger.debug(
                "%s failed: %s",
                executable,
                stderr.decode(
                    errors="ignore"
                ),
            )

        except FileNotFoundError:
            continue

        except asyncio.TimeoutError:
            logger.warning(
                "%s timed out.",
                executable,
            )

        except Exception:
            logger.exception(
                "%s TTS failed.",
                executable,
            )

    return None


# ============================================================
# SYNTHESIZE
# ============================================================

async def synthesize(
    text: str,
    language: Optional[str] = None,
    output_path: Optional[Path] = None,
) -> TTSResult:
    """
    Convert text into speech.
    """

    if not validate_text(
        text
    ):
        return TTSResult(
            text=text,
            success=False,
        )

    if output_path is None:
        output_path = build_output_path(
            ".wav"
        )

    try:

        provider = (
            TTS_PROVIDER
            or "system"
        ).lower().strip()

        if provider in (
            "system",
            "edge",
            "edge-tts",
        ):

            result = (
                await synthesize_with_system(
                    text=text,
                    output_path=output_path,
                    language=language,
                )
            )

            if result:

                return TTSResult(
                    audio_path=result,
                    text=text,
                    success=True,
                )

            return TTSResult(
                text=text,
                success=False,
            )

        logger.error(
            "Unsupported TTS provider: %s",
            provider,
        )

        return TTSResult(
            text=text,
            success=False,
        )

    except Exception:

        logger.exception(
            "TTS synthesis failed."
        )

        return TTSResult(
            text=text,
            success=False,
        )


# ============================================================
# TEXT TO SPEECH
# ============================================================

async def text_to_speech(
    text: str,
    language: Optional[str] = None,
) -> Optional[Path]:
    """
    Simple helper returning only the generated audio path.
    """

    result = await synthesize(
        text=text,
        language=language,
    )

    if not result:
        return None

    return result.audio_path


# ============================================================
# CHECK CONFIGURATION
# ============================================================

def is_tts_configured() -> bool:
    """
    Check whether the selected TTS provider is available.
    """

    provider = (
        TTS_PROVIDER
        or "system"
    ).lower().strip()

    if provider == "system":
        return True

    if provider in (
        "edge",
        "edge-tts",
    ):
        return True

    return False


# ============================================================
# CLEANUP
# ============================================================

def delete_tts_file(
    audio_path: Optional[Path],
) -> bool:
    """
    Delete generated TTS audio.
    """

    if not audio_path:
        return False

    try:

        if audio_path.exists():
            audio_path.unlink()

            logger.debug(
                "TTS file deleted: %s",
                audio_path,
            )

            return True

    except Exception:

        logger.exception(
            "Failed to delete TTS file."
        )

    return False


# ============================================================
# CLEAN ALL TTS FILES
# ============================================================

def cleanup_tts_files() -> int:
    """
    Delete all temporary TTS files.
    """

    directory = get_tts_directory()

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
                    "Failed to remove TTS file: %s",
                    file_path,
                )

    except Exception:

        logger.exception(
            "Failed to clean TTS directory."
        )

    if removed:
        logger.info(
            "Removed %s TTS files.",
            removed,
        )

    return removed


# ============================================================
# TTS SERVICE
# ============================================================

class TextToSpeech:
    """
    Reusable TTS service wrapper.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        language: Optional[str] = None,
    ):
        self.provider = (
            provider
            or TTS_PROVIDER
        )

        self.language = (
            language
            or TTS_LANGUAGE
        )

    async def synthesize(
        self,
        text: str,
    ) -> TTSResult:

        return await synthesize(
            text=text,
            language=self.language,
        )


# ============================================================
# DEFAULT SERVICE
# ============================================================

tts = TextToSpeech()
