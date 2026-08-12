# ai/intent.py

import logging
import re
from dataclasses import dataclass
from typing import Optional

from ai.prompts import get_intent_prompt


logger = logging.getLogger(__name__)


# ============================================================
# INTENTS
# ============================================================

NORMAL_CONVERSATION = "normal_conversation"

AI_QUESTION = "ai_question"

MUSIC_PLAY = "music_play"
MUSIC_SEARCH = "music_search"
MUSIC_PAUSE = "music_pause"
MUSIC_RESUME = "music_resume"
MUSIC_SKIP = "music_skip"
MUSIC_STOP = "music_stop"
MUSIC_QUEUE = "music_queue"
MUSIC_REMOVE = "music_remove"
MUSIC_VIDEO = "music_video"

VOICE_REQUEST = "voice_request"

HELP = "help"
SETTINGS = "settings"
SUBSCRIPTION = "subscription"
PAYMENT = "payment"

UNKNOWN = "unknown"


VALID_INTENTS = {
    NORMAL_CONVERSATION,
    AI_QUESTION,

    MUSIC_PLAY,
    MUSIC_SEARCH,
    MUSIC_PAUSE,
    MUSIC_RESUME,
    MUSIC_SKIP,
    MUSIC_STOP,
    MUSIC_QUEUE,
    MUSIC_REMOVE,
    MUSIC_VIDEO,

    VOICE_REQUEST,

    HELP,
    SETTINGS,
    SUBSCRIPTION,
    PAYMENT,

    UNKNOWN,
}


# ============================================================
# RESULT
# ============================================================

@dataclass
class IntentResult:
    intent: str
    confidence: float
    query: str
    metadata: Optional[dict] = None

    @property
    def is_music(self) -> bool:
        return self.intent.startswith("music_")

    @property
    def is_normal_chat(self) -> bool:
        return self.intent in {
            NORMAL_CONVERSATION,
            AI_QUESTION,
        }

    @property
    def is_payment_related(self) -> bool:
        return self.intent in {
            PAYMENT,
            SUBSCRIPTION,
        }


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(
    text: str,
) -> str:
    """
    Normalize Telegram text for intent detection.
    """

    text = str(text or "").strip().lower()

    # Remove repeated spaces.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


# ============================================================
# KEYWORD MATCHER
# ============================================================

def contains_any(
    text: str,
    words: list[str],
) -> bool:
    """
    Check whether any keyword exists in text.
    """

    return any(
        word in text
        for word in words
    )


# ============================================================
# MUSIC DETECTION
# ============================================================

MUSIC_PLAY_WORDS = [
    "play",
    "chalao",
    "chala",
    "bajao",
    "sunao",
    "suna do",
    "gana sunao",
    "gaana sunao",
    "baja do",
    "song chala",
    "gana chala",
    "gaana chala",
    "music chala",
    "music play",
    "start song",
    "start music",
]

MUSIC_SEARCH_WORDS = [
    "search song",
    "song search",
    "gana search",
    "gaana search",
    "music search",
    "find song",
    "find music",
    "search music",
]

MUSIC_PAUSE_WORDS = [
    "pause",
    "rok do",
    "rok",
    "song rok",
    "music rok",
    "pause song",
]

MUSIC_RESUME_WORDS = [
    "resume",
    "continue song",
    "song chalao",
    "fir se chalao",
    "phir se chalao",
    "music resume",
]

MUSIC_SKIP_WORDS = [
    "skip",
    "next song",
    "agla song",
    "next",
    "aage wala song",
    "song change",
]

MUSIC_STOP_WORDS = [
    "stop music",
    "stop song",
    "music stop",
    "song stop",
    "band karo music",
    "music band",
    "song band",
]

MUSIC_QUEUE_WORDS = [
    "queue",
    "playlist",
    "list songs",
    "song list",
    "queue dikhao",
    "playlist dikhao",
]

MUSIC_REMOVE_WORDS = [
    "remove song",
    "delete song",
    "queue se hatao",
    "song hatao",
    "remove from queue",
]


def detect_music_intent(
    text: str,
) -> Optional[str]:
    """
    Detect obvious music commands.
    """

    if contains_any(
        text,
        MUSIC_STOP_WORDS,
    ):
        return MUSIC_STOP

    if contains_any(
        text,
        MUSIC_PAUSE_WORDS,
    ):
        return MUSIC_PAUSE

    if contains_any(
        text,
        MUSIC_RESUME_WORDS,
    ):
        return MUSIC_RESUME

    if contains_any(
        text,
        MUSIC_SKIP_WORDS,
    ):
        return MUSIC_SKIP

    if contains_any(
        text,
        MUSIC_QUEUE_WORDS,
    ):
        return MUSIC_QUEUE

    if contains_any(
        text,
        MUSIC_REMOVE_WORDS,
    ):
        return MUSIC_REMOVE

    if contains_any(
        text,
        MUSIC_SEARCH_WORDS,
    ):
        return MUSIC_SEARCH

    if contains_any(text, ["video chalao", "video bajao", "video play", "video dikhao"]):
        return MUSIC_VIDEO

    if contains_any(
        text,
        MUSIC_PLAY_WORDS,
    ):
        return MUSIC_PLAY

    return None


# ============================================================
# VOICE DETECTION
# ============================================================

VOICE_WORDS = [
    "voice me bolo",
    "voice mein bolo",
    "voice reply",
    "voice response",
    "awaaz me bolo",
    "awaz me bolo",
    "audio me bolo",
    "audio bhejo",
    "voice bhejo",
    "speak",
    "bolkar batao",
]


def detect_voice_intent(
    text: str,
) -> bool:
    """
    Detect explicit voice response requests.
    """

    return contains_any(
        text,
        VOICE_WORDS,
    )


# ============================================================
# PAYMENT DETECTION
# ============================================================

PAYMENT_WORDS = [
    "payment",
    "pay",
    "paisa",
    "paise",
    "price",
    "cost",
    "stars",
    "telegram stars",
    "payment kaise",
    "payment karo",
    "payment karna",
    "buy",
    "purchase",
    "invoice",
]


def detect_payment_intent(
    text: str,
) -> bool:
    return contains_any(
        text,
        PAYMENT_WORDS,
    )


# ============================================================
# SUBSCRIPTION DETECTION
# ============================================================

SUBSCRIPTION_WORDS = [
    "premium",
    "subscription",
    "subscribe",
    "membership",
    "paid plan",
    "premium plan",
    "premium lena",
    "premium kaise",
    "premium activate",
    "renew",
    "renewal",
]


def detect_subscription_intent(
    text: str,
) -> bool:
    return contains_any(
        text,
        SUBSCRIPTION_WORDS,
    )


# ============================================================
# HELP DETECTION
# ============================================================

HELP_WORDS = [
    "help",
    "madad",
    "commands",
    "command list",
    "kya kar sakti ho",
    "kya kya kar sakti",
    "what can you do",
    "how to use",
]


def detect_help_intent(
    text: str,
) -> bool:
    return contains_any(
        text,
        HELP_WORDS,
    )


# ============================================================
# SETTINGS DETECTION
# ============================================================

SETTINGS_WORDS = [
    "settings",
    "setting",
    "configuration",
    "config",
    "preferences",
    "preference",
    "settings change",
]


def detect_settings_intent(
    text: str,
) -> bool:
    return contains_any(
        text,
        SETTINGS_WORDS,
    )


# ============================================================
# AI QUESTION DETECTION
# ============================================================

AI_QUESTION_WORDS = [
    "kya hai",
    "kya hota hai",
    "kaise",
    "kaise kare",
    "kaise karu",
    "kyun",
    "kyon",
    "why",
    "how",
    "what",
    "when",
    "where",
    "who",
    "explain",
    "samjhao",
    "batao",
    "tell me",
    "help me",
]


def detect_ai_question(
    text: str,
) -> bool:
    """
    Detect whether a message looks like a question.
    """

    if "?" in text:
        return True

    return contains_any(
        text,
        AI_QUESTION_WORDS,
    )


# ============================================================
# SIMPLE RULE-BASED DETECTOR
# ============================================================

def detect_rule_based(
    text: str,
) -> Optional[IntentResult]:
    """
    Fast local intent detection.

    This avoids an AI call for obvious commands.
    """

    normalized = normalize_text(
        text
    )

    if not normalized:
        return IntentResult(
            intent=UNKNOWN,
            confidence=1.0,
            query="",
        )

    # Music has priority.
    music_intent = detect_music_intent(
        normalized
    )

    if music_intent:
        return IntentResult(
            intent=music_intent,
            confidence=0.95,
            query=text,
        )

    # Explicit voice request.
    if detect_voice_intent(
        normalized
    ):
        return IntentResult(
            intent=VOICE_REQUEST,
            confidence=0.92,
            query=text,
        )

    # Payment before subscription because
    # "premium payment" can contain both.
    if detect_payment_intent(
        normalized
    ):
        return IntentResult(
            intent=PAYMENT,
            confidence=0.90,
            query=text,
        )

    if detect_subscription_intent(
        normalized
    ):
        return IntentResult(
            intent=SUBSCRIPTION,
            confidence=0.90,
            query=text,
        )

    if detect_settings_intent(
        normalized
    ):
        return IntentResult(
            intent=SETTINGS,
            confidence=0.88,
            query=text,
        )

    if detect_help_intent(
        normalized
    ):
        return IntentResult(
            intent=HELP,
            confidence=0.90,
            query=text,
        )

    if detect_ai_question(
        normalized
    ):
        return IntentResult(
            intent=AI_QUESTION,
            confidence=0.72,
            query=text,
        )

    return IntentResult(
        intent=NORMAL_CONVERSATION,
        confidence=0.65,
        query=text,
    )


# ============================================================
# GEMINI INTENT PARSER
# ============================================================

def parse_ai_intent(
    response: str,
    original_text: str,
) -> IntentResult:
    """
    Parse an AI-generated intent result.
    """

    value = normalize_text(
        response
    )

    # Remove common formatting.
    value = value.replace(
        "`",
        "",
    )

    value = value.strip(
        ".:; "
    )

    # Sometimes AI returns extra text.
    for intent in VALID_INTENTS:
        if value == intent:
            return IntentResult(
                intent=intent,
                confidence=0.85,
                query=original_text,
            )

    for intent in VALID_INTENTS:
        if intent in value:
            return IntentResult(
                intent=intent,
                confidence=0.70,
                query=original_text,
            )

    return IntentResult(
        intent=UNKNOWN,
        confidence=0.20,
        query=original_text,
    )


# ============================================================
# ASYNC AI DETECTION
# ============================================================

async def detect_intent_with_ai(
    text: str,
    ai_client=None,
    model: Optional[str] = None,
) -> IntentResult:
    """
    Detect intent using the AI client.

    The actual Gemini implementation is intentionally
    kept outside this module.

    ai_client is expected to provide a compatible
    text-generation method.
    """

    rule_result = detect_rule_based(
        text
    )

    # High-confidence local result does not need AI.
    if rule_result.confidence >= 0.90:
        return rule_result

    if ai_client is None:
        return rule_result

    prompt = get_intent_prompt(
        text
    )

    try:
        # Flexible interface:
        #
        # ai_client.generate_text(
        #     prompt,
        #     model=model
        # )
        #
        # The final brain.py will provide this interface.
        response = await ai_client.generate_text(
            prompt,
            model=model,
        )

        return parse_ai_intent(
            response=response,
            original_text=text,
        )

    except Exception:
        logger.exception(
            "AI intent detection failed."
        )

        return rule_result


# ============================================================
# MAIN DETECTOR
# ============================================================

async def detect_intent(
    text: str,
    ai_client=None,
    model: Optional[str] = None,
) -> IntentResult:
    """
    Main intent detection function.

    First uses fast local rules.
    Falls back to AI only when necessary.
    """

    if not text or not str(text).strip():
        return IntentResult(
            intent=UNKNOWN,
            confidence=1.0,
            query="",
        )

    return await detect_intent_with_ai(
        text=text,
        ai_client=ai_client,
        model=model,
    )


# ============================================================
# INTENT HELPERS
# ============================================================

def is_music_intent(
    intent: str,
) -> bool:
    return intent in {
        MUSIC_PLAY,
        MUSIC_SEARCH,
        MUSIC_VIDEO,
        MUSIC_PAUSE,
        MUSIC_RESUME,
        MUSIC_SKIP,
        MUSIC_STOP,
        MUSIC_QUEUE,
        MUSIC_REMOVE,
    }


def is_command_intent(
    intent: str,
) -> bool:
    return intent in {
        MUSIC_PLAY,
        MUSIC_SEARCH,
        MUSIC_VIDEO,
        MUSIC_PAUSE,
        MUSIC_RESUME,
        MUSIC_SKIP,
        MUSIC_STOP,
        MUSIC_QUEUE,
        MUSIC_REMOVE,
        VOICE_REQUEST,
        HELP,
        SETTINGS,
        SUBSCRIPTION,
        PAYMENT,
    }


def is_ai_intent(
    intent: str,
) -> bool:
    return intent in {
        NORMAL_CONVERSATION,
        AI_QUESTION,
    }


def requires_ai_response(
    intent: str,
) -> bool:
    """
    Determine whether Gemini should generate a response.

    Music operations may be handled by music/player.py.
    Payment/subscription commands may be handled by
    their respective modules.
    """

    return intent in {
        NORMAL_CONVERSATION,
        AI_QUESTION,
        HELP,
        SETTINGS,
        SUBSCRIPTION,
        PAYMENT,
        VOICE_REQUEST,
    }


# ============================================================
# EXTRACT MUSIC QUERY
# ============================================================

def extract_music_query(
    text: str,
) -> str:
    """
    Extract a probable song/search query from a music command.

    Examples:

        "play Arijit Singh"
            -> "Arijit Singh"

        "gana chalao Kesariya"
            -> "Kesariya"
    """

    original = str(
        text or ""
    ).strip()

    normalized = normalize_text(
        original
    )

    prefixes = [
        "play ",
        "search ",
        "song ",
        "music ",
        "gana ",
        "gaana ",
        "chalao ",
        "bajao ",
        "play song ",
        "play music ",
        "song chalao ",
        "gana chalao ",
        "gaana chalao ",
    ]

    for prefix in prefixes:
        if normalized.startswith(
            prefix
        ):
            result = original[
                len(prefix):
            ].strip()

            if result:
                return result

    # Try common Hindi command phrases.
    patterns = [
        r"(?:chalao|bajao|chala)\s+(.+)",
        r"(?:play|search)\s+(.+)",
        r"(?:song|gana|gaana|music)\s+(.+)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            original,
            flags=re.IGNORECASE,
        )

        if match:
            result = match.group(
                1
            ).strip()

            if result:
                return result

    return original


# ============================================================
# INTENT DISPLAY NAME
# ============================================================

INTENT_NAMES = {
    NORMAL_CONVERSATION: "Normal Conversation",
    AI_QUESTION: "AI Question",

    MUSIC_PLAY: "Play Music",
    MUSIC_SEARCH: "Search Music",
    MUSIC_PAUSE: "Pause Music",
    MUSIC_RESUME: "Resume Music",
    MUSIC_SKIP: "Skip Music",
    MUSIC_STOP: "Stop Music",
    MUSIC_QUEUE: "Music Queue",
    MUSIC_REMOVE: "Remove Song",

    VOICE_REQUEST: "Voice Request",

    HELP: "Help",
    SETTINGS: "Settings",
    SUBSCRIPTION: "Subscription",
    PAYMENT: "Payment",
    UNKNOWN: "Unknown",
}


def get_intent_name(
    intent: str,
) -> str:
    return INTENT_NAMES.get(
        intent,
        "Unknown",
)
