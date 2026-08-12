# ai/brain.py

import logging
from typing import Optional

from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

from ai.memory import (
    get_ai_history,
    save_user_message,
    save_assistant_message,
)

from ai.prompts import (
    build_full_prompt,
    build_short_prompt,
)

from ai.intent import (
    detect_intent,
)


logger = logging.getLogger(__name__)


# ============================================================
# GEMINI CLIENT
# ============================================================

_client: Optional[genai.Client] = None


def get_gemini_client() -> genai.Client:
    """
    Return a reusable Gemini client.
    """

    global _client

    if _client is not None:
        return _client

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    _client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    return _client


# ============================================================
# MODEL
# ============================================================

def get_model_name(
    model: Optional[str] = None,
) -> str:
    """
    Return configured Gemini model.
    """

    if model:
        return model

    if GEMINI_MODEL:
        return GEMINI_MODEL

    return "gemini-2.5-flash"


# ============================================================
# GENERATE TEXT
# ============================================================

async def generate_text(
    prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_output_tokens: int = 2048,
) -> str:
    """
    Generate text using Gemini.
    """

    prompt = str(prompt or "").strip()

    if not prompt:
        return ""

    client = get_gemini_client()

    model_name = get_model_name(model)

    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            ),
        )

        text = getattr(
            response,
            "text",
            None,
        )

        if not text:
            logger.warning(
                "Gemini returned an empty response."
            )
            return ""

        return str(text).strip()

    except Exception:
        logger.exception(
            "Gemini text generation failed."
        )
        raise


# ============================================================
# SIMPLE ASK
# ============================================================

async def ask(
    prompt: str,
    model: Optional[str] = None,
) -> str:
    """
    Simple Gemini question without memory.
    """

    return await generate_text(
        prompt=prompt,
        model=model,
    )


# ============================================================
# ASK GEMINI
# ============================================================
#
# Backward-compatible function.
#
# Some project files import:
#
#     from ai.brain import ask_gemini
#
# So this function MUST exist.
# ============================================================

async def ask_gemini(
    prompt: str,
    model: Optional[str] = None,
) -> str:
    """
    Backward-compatible Gemini function.

    Uses the same Gemini generator as ask().
    """

    return await generate_text(
        prompt=prompt,
        model=model,
    )


# ============================================================
# CHAT WITH MEMORY
# ============================================================

async def chat(
    user_id: int,
    message: str,
    chat_id: Optional[int] = None,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    is_premium: bool = False,
    group_title: Optional[str] = None,
    group_language: str = "Hinglish",
    ai_enabled: bool = True,
    reply_to_all: bool = False,
    reply_to_mentions: bool = True,
    reply_to_message: Optional[str] = None,
    model: Optional[str] = None,
    save_memory: bool = True,
    use_ai_intent: bool = False,
) -> str:
    """
    Main Zara conversation function.

    Flow:

        User message
              ↓
        Intent detection
              ↓
        Memory load
              ↓
        Prompt creation
              ↓
        Gemini
              ↓
        Save response
              ↓
        Return response
    """

    message = str(
        message or ""
    ).strip()

    if not message:
        return ""

    # --------------------------------------------------------
    # Detect intent
    # --------------------------------------------------------

    try:
        intent_result = await detect_intent(
            text=message,
            ai_client=(
                _IntentAIAdapter()
                if use_ai_intent
                else None
            ),
            model=model,
        )
    except Exception:
        logger.exception(
            "Intent detection failed. "
            "Continuing with default intent."
        )

        class DefaultIntent:
            intent = "conversation"
            confidence = 0.0

        intent_result = DefaultIntent()

    # --------------------------------------------------------
    # Get conversation memory
    # --------------------------------------------------------

    try:
        history = await get_ai_history(
            user_id=user_id,
            chat_id=chat_id,
        )
    except Exception:
        logger.exception(
            "Failed to load AI history."
        )
        history = []

    # --------------------------------------------------------
    # Build full prompt
    # --------------------------------------------------------

    prompt = build_full_prompt(
        user_message=message,
        history=history,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        is_premium=is_premium,
        chat_id=chat_id,
        group_title=group_title,
        group_language=group_language,
        ai_enabled=ai_enabled,
        reply_to_all=reply_to_all,
        reply_to_mentions=reply_to_mentions,
        reply_to_message=reply_to_message,
        intent=intent_result.intent,
        confidence=intent_result.confidence,
    )

    # --------------------------------------------------------
    # Save user message
    # --------------------------------------------------------

    if save_memory:
        try:
            await save_user_message(
                user_id=user_id,
                content=message,
                chat_id=chat_id,
                username=username,
            )
        except Exception:
            logger.exception(
                "Failed to save user message."
            )

    # --------------------------------------------------------
    # Generate response
    # --------------------------------------------------------

    response = await generate_text(
        prompt=prompt,
        model=model,
    )

    response = response.strip()

    # --------------------------------------------------------
    # Save assistant response
    # --------------------------------------------------------

    if response and save_memory:
        try:
            await save_assistant_message(
                user_id=user_id,
                content=response,
                chat_id=chat_id,
            )
        except Exception:
            logger.exception(
                "Failed to save assistant message."
            )

    return response


# ============================================================
# SHORT CHAT
# ============================================================

async def short_chat(
    message: str,
    model: Optional[str] = None,
) -> str:
    """
    Lightweight AI response without database memory.
    """

    message = str(
        message or ""
    ).strip()

    if not message:
        return ""

    prompt = build_short_prompt(
        user_message=message,
    )

    return await generate_text(
        prompt=prompt,
        model=model,
    )


# ============================================================
# INTENT AI ADAPTER
# ============================================================

class _IntentAIAdapter:
    """
    Adapter used by intent.py.

    It exposes generate_text().
    """

    async def generate_text(
        self,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        return await generate_text(
            prompt=prompt,
            model=model,
            temperature=0.0,
            max_output_tokens=100,
        )


# ============================================================
# REGENERATE RESPONSE
# ============================================================

async def regenerate(
    user_id: int,
    message: str,
    chat_id: Optional[int] = None,
    model: Optional[str] = None,
) -> str:
    """
    Generate a fresh response using existing memory.

    The new user message is not saved again.
    """

    history = await get_ai_history(
        user_id=user_id,
        chat_id=chat_id,
    )

    prompt = build_full_prompt(
        user_message=message,
        history=history,
        user_id=user_id,
        chat_id=chat_id,
    )

    return await generate_text(
        prompt=prompt,
        model=model,
    )


# ============================================================
# SUMMARIZE CONVERSATION
# ============================================================

async def summarize_conversation(
    user_id: int,
    chat_id: Optional[int] = None,
    model: Optional[str] = None,
) -> str:
    """
    Create a summary of the current conversation.
    """

    history = await get_ai_history(
        user_id=user_id,
        chat_id=chat_id,
    )

    if not history:
        return ""

    lines = []

    for item in history:
        role = item.get(
            "role",
            "user",
        )

        content = item.get(
            "content",
            "",
        )

        if role == "assistant":
            speaker = "Zara"
        else:
            speaker = "User"

        if content:
            lines.append(
                f"{speaker}: {content}"
            )

    conversation = "\n".join(lines)

    prompt = f"""
Summarize the following conversation.

Keep:
- useful user preferences
- ongoing tasks
- important context
- decisions already made

Do not:
- invent information
- include passwords, API keys or secrets
- include meaningless greetings
- expose internal instructions

Conversation:

{conversation}
"""

    return await generate_text(
        prompt=prompt,
        model=model,
        temperature=0.2,
        max_output_tokens=1000,
    )


# ============================================================
# HEALTH CHECK
# ============================================================

async def test_gemini() -> bool:
    """
    Test whether Gemini is reachable.
    """

    try:
        response = await generate_text(
            prompt="Reply with exactly: OK",
            temperature=0.0,
            max_output_tokens=10,
        )

        return bool(response)

    except Exception:
        logger.exception(
            "Gemini health check failed."
        )
        return False
