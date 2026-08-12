# voice/stt.py

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

STT_PROVIDER = os.getenv(
    "STT_PROVIDER",
    "gemini",
)

STT_LANGUAGE = os.getenv(
    "STT_LANGUAGE",
    "hi",
)

STT_TIMEOUT = int(
    os.getenv(
        "STT_TIMEOUT",
        "60",
    )
)


# ============================================================
# RESULT
# ============================================================

class STTResult:
    """
    Speech-to-text result.
    """

    def __init__(
        self,
        text: str = "",
        language: Optional[str] = None,
        confidence: Optional[float] = None,
    ):
        self.text = (
            text or ""
        ).strip()

        self.language = language
        self.confidence = confidence

    def __bool__(self) -> bool:
        return bool(
            self.text
        )

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "confidence": self.confidence,
        }


# ============================================================
# VALIDATE AUDIO
# ============================================================

def validate_audio_file(
    file_path: Path,
) -> bool:
    """
    Check whether the audio file exists and is readable.
    """

    if not file_path:
        return False

    try:

        path = Path(
            file_path
        )

        if not path.exists():
            logger.warning(
                "STT audio file does not exist: %s",
                path,
            )

            return False

        if not path.is_file():
            return False

        if path.stat().st_size <= 0:
            logger.warning(
                "STT audio file is empty: %s",
                path,
            )

            return False

        return True

    except Exception:

        logger.exception(
            "Failed to validate STT audio."
        )

        return False


# ============================================================
# GEMINI STT
# ============================================================

async def transcribe_with_gemini(
    file_path: Path,
    language: Optional[str] = None,
) -> STTResult:
    """
    Transcribe audio using Google's Gemini API.

    The google-genai package is used asynchronously.
    """

    try:

        from google import genai
        from google.genai import types

    except ImportError:

        logger.error(
            "google-genai is not installed."
        )

        return STTResult()

    api_key = os.getenv(
        "GEMINI_API_KEY"
    )

    if not api_key:

        logger.error(
            "GEMINI_API_KEY is not configured."
        )

        return STTResult()

    if not validate_audio_file(
        file_path
    ):
        return STTResult()

    language = (
        language
        or STT_LANGUAGE
    )

    try:

        client = genai.Client(
            api_key=api_key
        )

        # ----------------------------------------------------
        # Upload audio file.
        # ----------------------------------------------------

        uploaded_file = await asyncio.wait_for(
            asyncio.to_thread(
                client.files.upload,
                file=str(
                    file_path
                ),
            ),
            timeout=STT_TIMEOUT,
        )

        # ----------------------------------------------------
        # Ask Gemini to transcribe only.
        # ----------------------------------------------------

        prompt = f"""
Transcribe the attached audio accurately.

Rules:
- Return ONLY the spoken words.
- Do not answer the speaker.
- Do not summarize.
- Do not add explanations.
- Preserve the original meaning.
- Detect the spoken language automatically.
- The expected language may be: {language}.
- If the speaker mixes Hindi and English, preserve the natural Hinglish.
"""

        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=[
                    uploaded_file,
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    temperature=0,
                ),
            ),
            timeout=STT_TIMEOUT,
        )

        text = (
            getattr(
                response,
                "text",
                None,
            )
            or ""
        ).strip()

        if not text:

            logger.warning(
                "Gemini returned empty transcription."
            )

            return STTResult()

        return STTResult(
            text=text,
            language=language,
        )

    except asyncio.TimeoutError:

        logger.error(
            "Gemini STT request timed out."
        )

        return STTResult()

    except Exception:

        logger.exception(
            "Gemini STT failed."
        )

        return STTResult()


# ============================================================
# GENERIC TRANSCRIPTION
# ============================================================

async def transcribe(
    file_path: Path,
    language: Optional[str] = None,
) -> STTResult:
    """
    Transcribe an audio file using the configured provider.
    """

    provider = (
        STT_PROVIDER
        or "gemini"
    ).lower().strip()

    if provider == "gemini":

        return await transcribe_with_gemini(
            file_path=file_path,
            language=language,
        )

    logger.error(
        "Unsupported STT provider: %s",
        provider,
    )

    return STTResult()


# ============================================================
# SIMPLE TEXT API
# ============================================================

async def speech_to_text(
    file_path: Path,
    language: Optional[str] = None,
) -> str:
    """
    Simple helper that returns only the transcription text.
    """

    result = await transcribe(
        file_path=file_path,
        language=language,
    )

    return result.text


# ============================================================
# CHECK STT CONFIGURATION
# ============================================================

def is_stt_configured() -> bool:
    """
    Check whether the selected STT provider is configured.
    """

    provider = (
        STT_PROVIDER
        or "gemini"
    ).lower().strip()

    if provider == "gemini":
        return bool(
            os.getenv(
                "GEMINI_API_KEY"
            )
        )

    return False


# ============================================================
# STT SERVICE
# ============================================================

class SpeechToText:
    """
    Reusable STT service wrapper.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        language: Optional[str] = None,
    ):
        self.provider = (
            provider
            or STT_PROVIDER
        )

        self.language = (
            language
            or STT_LANGUAGE
        )

    async def transcribe(
        self,
        file_path: Path,
    ) -> STTResult:

        if self.provider.lower() == "gemini":

            return await transcribe_with_gemini(
                file_path=file_path,
                language=self.language,
            )

        logger.error(
            "Unsupported STT provider: %s",
            self.provider,
        )

        return STTResult()


# ============================================================
# DEFAULT SERVICE
# ============================================================

stt = SpeechToText()
