# config.py

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


# ============================================================
# BASE PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


# ============================================================
# ENVIRONMENT HELPERS
# ============================================================

def get_env(
    name: str,
    default: Optional[str] = None,
    required: bool = False,
) -> str:
    value = os.getenv(name, default)

    if required and (
        value is None
        or str(value).strip() == ""
    ):
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value


def get_int(
    name: str,
    default: int = 0,
    required: bool = False,
) -> int:
    value = get_env(
        name,
        str(default),
        required,
    )

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Environment variable {name} must be an integer."
        ) from exc


def get_bool(
    name: str,
    default: bool = False,
) -> bool:
    value = get_env(
        name,
        "true" if default else "false",
    )

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def parse_id_list(
    value: str,
) -> list[int]:
    if not value:
        return []

    result: list[int] = []

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            result.append(int(item))
        except ValueError:
            continue

    return result


# ============================================================
# APPLICATION
# ============================================================

APP_NAME = get_env(
    "APP_NAME",
    "Zara AI",
)

APP_VERSION = get_env(
    "APP_VERSION",
    "1.0.0",
)

ENVIRONMENT = get_env(
    "ENVIRONMENT",
    "production",
).lower()

DEBUG = get_bool(
    "DEBUG",
    False,
)

LOG_LEVEL = get_env(
    "LOG_LEVEL",
    "INFO",
).upper()

LOG_FILE = get_env(
    "LOG_FILE",
    "data/zara.log",
)
# ============================================================
# TELEGRAM API
# ============================================================

API_ID = get_int(
    "API_ID",
    required=True,
)

API_HASH = get_env(
    "API_HASH",
    required=True,
)


# ============================================================
# MANAGER BOT
# ============================================================
#
# Preferred variable:
#
# MANAGER_BOT_TOKEN
#
# BOT_TOKEN is also accepted for compatibility
# with older project files.
# ============================================================

BOT_TOKEN = get_env(
    "MANAGER_BOT_TOKEN",
    None,
)

if not BOT_TOKEN:
    BOT_TOKEN = get_env(
        "BOT_TOKEN",
        None,
    )

if not BOT_TOKEN:
    raise RuntimeError(
        "Missing required environment variable: "
        "MANAGER_BOT_TOKEN"
    )

MANAGER_BOT_TOKEN = BOT_TOKEN


# ============================================================
# TELETHON USERBOT
# ============================================================
#
# Preferred:
#
# SESSION_STRING
#
# STRING_SESSION remains supported for compatibility.
# ============================================================

SESSION_STRING = get_env(
    "SESSION_STRING",
    None,
)

if SESSION_STRING is None:
    SESSION_STRING = get_env(
        "STRING_SESSION",
        "",
    )

STRING_SESSION = SESSION_STRING


# ============================================================
# OWNER
# ============================================================

OWNER_ID = get_int(
    "OWNER_ID",
    required=True,
)


# ============================================================
# OPTIONAL SUDO USERS
# ============================================================

SUDO_USERS = parse_id_list(
    get_env(
        "SUDO_USERS",
        "",
    )
)

if OWNER_ID not in SUDO_USERS:
    SUDO_USERS.insert(
        0,
        OWNER_ID,
    )


# ============================================================
# AI
# ============================================================

AI_NAME = get_env(
    "AI_NAME",
    "Zara",
)

AI_LANGUAGE = get_env(
    "AI_LANGUAGE",
    "Hinglish",
)

AI_PERSONALITY = get_env(
    "AI_PERSONALITY",
    (
        "You are Zara, a friendly Telegram Voice Chat AI "
        "assistant. Speak naturally in Hindi, Hinglish and "
        "English. Keep spoken answers short, natural and "
        "conversational. Do not use unnecessary markdown. "
        "Do not include URLs in spoken responses. "
        "Do not claim to be human."
    ),
)

GEMINI_API_KEY = get_env(
    "GEMINI_API_KEY",
    required=True,
)

GEMINI_MODEL = get_env(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)

AI_MAX_HISTORY = get_int(
    "AI_MAX_HISTORY",
    20,
)


# ============================================================
# MONGODB
# ============================================================
#
# Preferred:
#
# MONGODB_URI
# MONGODB_DATABASE
#
# Old names remain supported.
# ============================================================

MONGO_URI = get_env(
    "MONGODB_URI",
    None,
)

if not MONGO_URI:
    MONGO_URI = get_env(
        "MONGO_URI",
        None,
    )

if not MONGO_URI:
    raise RuntimeError(
        "Missing required environment variable: "
        "MONGODB_URI"
    )


MONGO_DB_NAME = get_env(
    "MONGODB_DATABASE",
    None,
)

if not MONGO_DB_NAME:
    MONGO_DB_NAME = get_env(
        "MONGO_DB_NAME",
        "zara_ai",
    )

MONGODB_URI = MONGO_URI
MONGODB_DATABASE = MONGO_DB_NAME


# ============================================================
# DATABASE COLLECTIONS
# ============================================================

USERS_COLLECTION = get_env(
    "USERS_COLLECTION",
    "users",
)

GROUPS_COLLECTION = get_env(
    "GROUPS_COLLECTION",
    "groups",
)

MEMORY_COLLECTION = get_env(
    "MEMORY_COLLECTION",
    "memory",
)

SUBSCRIPTIONS_COLLECTION = get_env(
    "SUBSCRIPTIONS_COLLECTION",
    "subscriptions",
)

PAYMENTS_COLLECTION = get_env(
    "PAYMENTS_COLLECTION",
    "payments",
)

SETTINGS_COLLECTION = get_env(
    "SETTINGS_COLLECTION",
    "settings",
)


# ============================================================
# TELEGRAM SUPPORT / UPDATES
# ============================================================

SUPPORT_URL = get_env(
    "SUPPORT_URL",
    "",
)

UPDATES_URL = get_env(
    "UPDATES_URL",
    "",
)

AARU_BOT_USERNAME = get_env(
    "AARU_BOT_USERNAME",
    "",
)


# ============================================================
# VOICE
# ============================================================

VOICE_ENABLED = get_bool(
    "VOICE_ENABLED",
    True,
)

STT_PROVIDER = get_env(
    "STT_PROVIDER",
    "external",
).lower()

TTS_PROVIDER = get_env(
    "TTS_PROVIDER",
    "external",
).lower()

STT_API_KEY = get_env(
    "STT_API_KEY",
    "",
)

TTS_API_KEY = get_env(
    "TTS_API_KEY",
    "",
)

STT_API_URL = get_env(
    "STT_API_URL",
    "",
)

TTS_API_URL = get_env(
    "TTS_API_URL",
    "",
)

VOICE_LANGUAGE = get_env(
    "VOICE_LANGUAGE",
    "hi-IN",
)

TTS_VOICE = get_env(
    "TTS_VOICE",
    "hi-IN-SwaraNeural",
)


# ============================================================
# MUSIC
# ============================================================

MUSIC_ENABLED = get_bool(
    "MUSIC_ENABLED",
    True,
)

MUSIC_MAX_QUEUE = get_int(
    "MUSIC_MAX_QUEUE",
    20,
)

MUSIC_MAX_FILE_SIZE_MB = get_int(
    "MUSIC_MAX_FILE_SIZE_MB",
    100,
)


# ============================================================
# AUDIO / FFMPEG
# ============================================================

FFMPEG_PATH = get_env(
    "FFMPEG_PATH",
    "ffmpeg",
)

FFPROBE_PATH = get_env(
    "FFPROBE_PATH",
    "ffprobe",
)


# ============================================================
# PYTGCalls
# ============================================================

PYTGCALLS_ENABLED = get_bool(
    "PYTGCALLS_ENABLED",
    True,
)


# ============================================================
# SUBSCRIPTIONS
# ============================================================

SUBSCRIPTIONS_ENABLED = get_bool(
    "SUBSCRIPTIONS_ENABLED",
    True,
)

FREE_PLAN_NAME = get_env(
    "FREE_PLAN_NAME",
    "Free",
)

PREMIUM_PLAN_NAME = get_env(
    "PREMIUM_PLAN_NAME",
    "Premium",
)

PREMIUM_DURATION_DAYS = get_int(
    "PREMIUM_DURATION_DAYS",
    30,
)


# ============================================================
# TELEGRAM STARS
# ============================================================

STARS_ENABLED = get_bool(
    "STARS_ENABLED",
    True,
)

# Zara requirement:
#
# 50 Telegram Stars
# 30 days
# 1 group/channel
#
PREMIUM_STARS_PRICE = get_int(
    "PREMIUM_STARS_PRICE",
    50,
)

STARS_CURRENCY = "XTR"


# ============================================================
# FILE STORAGE
# ============================================================

DATA_DIR = BASE_DIR / "data"

DOWNLOAD_DIR = (
    DATA_DIR / "downloads"
)

CACHE_DIR = (
    DATA_DIR / "cache"
)

TEMP_DIR = (
    DATA_DIR / "temp"
)

SESSION_DIR = (
    DATA_DIR / "sessions"
)

MUSIC_DOWNLOAD_DIR = (
    DOWNLOAD_DIR / "music"
)


for directory in (
    DATA_DIR,
    DOWNLOAD_DIR,
    CACHE_DIR,
    TEMP_DIR,
    SESSION_DIR,
    MUSIC_DOWNLOAD_DIR,
):
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# RUNTIME LIMITS
# ============================================================

TEMP_FILE_MAX_AGE_SECONDS = get_int(
    "TEMP_FILE_MAX_AGE_SECONDS",
    3600,
)

MAX_VOICE_DURATION_SECONDS = get_int(
    "MAX_VOICE_DURATION_SECONDS",
    60,
)

MAX_MEMORY_MESSAGES = get_int(
    "MAX_MEMORY_MESSAGES",
    20,
)


# ============================================================
# SCHEDULER
# ============================================================

SCHEDULER_ENABLED = get_bool(
    "SCHEDULER_ENABLED",
    True,
)

SUBSCRIPTION_CHECK_INTERVAL_SECONDS = get_int(
    "SUBSCRIPTION_CHECK_INTERVAL_SECONDS",
    300,
)

REMINDER_HOURS_BEFORE_EXPIRY = get_int(
    "REMINDER_HOURS_BEFORE_EXPIRY",
    24,
)


# ============================================================
# VALIDATION
# ============================================================

def validate_config() -> bool:
    """
    Validate critical Zara configuration.
    """

    if API_ID <= 0:
        raise RuntimeError(
            "API_ID must be a positive integer."
        )

    if not API_HASH.strip():
        raise RuntimeError(
            "API_HASH cannot be empty."
        )

    if not BOT_TOKEN.strip():
        raise RuntimeError(
            "MANAGER_BOT_TOKEN cannot be empty."
        )

    if OWNER_ID <= 0:
        raise RuntimeError(
            "OWNER_ID must be a positive integer."
        )

    if not MONGO_URI.strip():
        raise RuntimeError(
            "MONGODB_URI cannot be empty."
        )

    if not MONGO_DB_NAME.strip():
        raise RuntimeError(
            "MONGODB_DATABASE cannot be empty."
        )

    if not GEMINI_API_KEY.strip():
        raise RuntimeError(
            "GEMINI_API_KEY cannot be empty."
        )

    if PREMIUM_STARS_PRICE != 50:
        raise RuntimeError(
            "PREMIUM_STARS_PRICE must be 50 "
            "for the Zara subscription plan."
        )

    if PREMIUM_DURATION_DAYS != 30:
        raise RuntimeError(
            "PREMIUM_DURATION_DAYS must be 30 "
            "for the Zara subscription plan."
        )

    return True


# ============================================================
# ENVIRONMENT HELPERS
# ============================================================

def is_development() -> bool:
    return ENVIRONMENT in {
        "development",
        "dev",
        "testing",
        "test",
    }


def is_production() -> bool:
    return ENVIRONMENT in {
        "production",
        "prod",
    }


# ============================================================
# SAFE CONFIG SUMMARY
# ============================================================

def get_config_summary() -> dict:
    """
    Return configuration information without secrets.
    """

    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
        "environment": ENVIRONMENT,
        "debug": DEBUG,
        "ai_name": AI_NAME,
        "gemini_model": GEMINI_MODEL,
        "mongo_db": MONGO_DB_NAME,
        "voice_enabled": VOICE_ENABLED,
        "music_enabled": MUSIC_ENABLED,
        "subscriptions_enabled": SUBSCRIPTIONS_ENABLED,
        "stars_enabled": STARS_ENABLED,
        "pytgcalls_enabled": PYTGCALLS_ENABLED,
        "scheduler_enabled": SCHEDULER_ENABLED,
        "owner_id": OWNER_ID,
        "premium_stars": PREMIUM_STARS_PRICE,
        "premium_days": PREMIUM_DURATION_DAYS,
    }
