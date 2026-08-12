# database/settings.py

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database.mongodb import settings as settings_collection

logger = logging.getLogger(__name__)


# ============================================================
# TIME HELPER
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULT_SETTINGS = {
    "access_mode": "free",

    "ai_enabled": True,
    "voice_enabled": True,
    "music_enabled": True,

    "maintenance_mode": False,

    "premium_stars": 50,
    "premium_duration_days": 30,

    "updated_at": None,
}


# ============================================================
# SETTING KEY VALIDATION
# ============================================================

def _validate_key(key: str) -> str:
    """
    Validate a MongoDB setting key.
    """

    key = str(key).strip()

    if not key:
        raise ValueError(
            "Setting key cannot be empty."
        )

    if key.startswith("$"):
        raise ValueError(
            "Invalid setting key."
        )

    if "." in key:
        raise ValueError(
            "Setting key cannot contain '.'."
        )

    return key


# ============================================================
# GET SETTING DOCUMENT
# ============================================================

async def get_setting_document(
    key: str,
) -> Optional[dict[str, Any]]:
    """
    Get a setting document by key.
    """

    key = _validate_key(key)

    return await settings_collection().find_one(
        {
            "key": key,
        }
    )


# ============================================================
# GET SETTING
# ============================================================

async def get_setting(
    key: str,
    default: Any = None,
) -> Any:
    """
    Get a setting value.

    Returns default if the setting does not exist.
    """

    document = await get_setting_document(key)

    if document is None:
        return default

    return document.get(
        "value",
        default,
    )


# ============================================================
# SET SETTING
# ============================================================

async def set_setting(
    key: str,
    value: Any,
) -> bool:
    """
    Create or update a global Zara setting.

    Settings are stored persistently in MongoDB.
    """

    key = _validate_key(key)
    now = utc_now()

    result = await settings_collection().update_one(
        {
            "key": key,
        },
        {
            "$set": {
                "value": value,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            },
        },
        upsert=True,
    )

    return (
        result.modified_count > 0
        or result.upserted_id is not None
    )


# ============================================================
# DELETE SETTING
# ============================================================

async def delete_setting(
    key: str,
) -> bool:
    """
    Delete a global setting.
    """

    key = _validate_key(key)

    result = await settings_collection().delete_one(
        {
            "key": key,
        }
    )

    return result.deleted_count > 0


# ============================================================
# GET ALL SETTINGS
# ============================================================

async def get_all_settings() -> dict[str, Any]:
    """
    Return all global settings as:

        {
            "key": value
        }
    """

    cursor = settings_collection().find({})

    documents = await cursor.to_list(
        length=None
    )

    return {
        document["key"]: document.get(
            "value"
        )
        for document in documents
        if "key" in document
    }


# ============================================================
# INITIALIZE DEFAULT SETTINGS
# ============================================================

async def initialize_settings() -> None:
    """
    Create default settings if they do not exist.

    Existing values are NEVER overwritten.
    """

    now = utc_now()

    for key, value in DEFAULT_SETTINGS.items():

        if key == "updated_at":
            continue

        existing = await settings_collection().find_one(
            {
                "key": key,
            },
            {
                "_id": 1,
            },
        )

        if existing is not None:
            continue

        await settings_collection().insert_one(
            {
                "key": key,
                "value": value,
                "created_at": now,
                "updated_at": now,
            }
        )

    logger.info(
        "Default Zara settings initialized."
    )


# ============================================================
# ACCESS MODE
# ============================================================

async def get_access_mode() -> str:
    """
    Return current global access mode.

    Possible values:

        free
        paid
    """

    value = await get_setting(
        "access_mode",
        "free",
    )

    value = str(value).strip().lower()

    if value not in {
        "free",
        "paid",
    }:
        logger.warning(
            "Invalid access_mode '%s'. Falling back to free.",
            value,
        )

        return "free"

    return value


async def set_access_mode(
    mode: str,
) -> bool:
    """
    Set global Zara access mode.

    Only:
        free
        paid
    """

    mode = str(mode).strip().lower()

    if mode not in {
        "free",
        "paid",
    }:
        raise ValueError(
            "Access mode must be 'free' or 'paid'."
        )

    return await set_setting(
        "access_mode",
        mode,
    )


async def is_free_mode() -> bool:
    return (
        await get_access_mode()
        == "free"
    )


async def is_paid_mode() -> bool:
    return (
        await get_access_mode()
        == "paid"
    )


# ============================================================
# AI SETTINGS
# ============================================================

async def is_ai_enabled() -> bool:
    return bool(
        await get_setting(
            "ai_enabled",
            True,
        )
    )


async def set_ai_enabled(
    enabled: bool,
) -> bool:
    return await set_setting(
        "ai_enabled",
        bool(enabled),
    )


# ============================================================
# VOICE SETTINGS
# ============================================================

async def is_voice_enabled() -> bool:
    return bool(
        await get_setting(
            "voice_enabled",
            True,
        )
    )


async def set_voice_enabled(
    enabled: bool,
) -> bool:
    return await set_setting(
        "voice_enabled",
        bool(enabled),
    )


# ============================================================
# MUSIC SETTINGS
# ============================================================

async def is_music_enabled() -> bool:
    return bool(
        await get_setting(
            "music_enabled",
            True,
        )
    )


async def set_music_enabled(
    enabled: bool,
) -> bool:
    return await set_setting(
        "music_enabled",
        bool(enabled),
    )


# ============================================================
# MAINTENANCE MODE
# ============================================================

async def is_maintenance_mode() -> bool:
    return bool(
        await get_setting(
            "maintenance_mode",
            False,
        )
    )


async def set_maintenance_mode(
    enabled: bool,
) -> bool:
    return await set_setting(
        "maintenance_mode",
        bool(enabled),
    )


# ============================================================
# PREMIUM SETTINGS
# ============================================================

async def get_premium_price() -> int:
    """
    Return current Telegram Stars price.

    Zara default:
        50 XTR
    """

    value = await get_setting(
        "premium_stars",
        50,
    )

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return 50


async def set_premium_price(
    stars: int,
) -> bool:
    """
    Set premium Telegram Stars price.
    """

    stars = int(stars)

    if stars <= 0:
        raise ValueError(
            "Premium Stars price must be greater than 0."
        )

    return await set_setting(
        "premium_stars",
        stars,
    )


async def get_premium_duration_days() -> int:
    """
    Return premium subscription duration.
    """

    value = await get_setting(
        "premium_duration_days",
        30,
    )

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return 30


async def set_premium_duration_days(
    days: int,
) -> bool:
    """
    Set premium subscription duration.
    """

    days = int(days)

    if days <= 0:
        raise ValueError(
            "Premium duration must be greater than 0."
        )

    return await set_setting(
        "premium_duration_days",
        days,
    )


# ============================================================
# RESET SETTINGS
# ============================================================

async def reset_setting(
    key: str,
) -> bool:
    """
    Reset a setting to its default value.

    If the setting has no defined default, it is deleted.
    """

    key = _validate_key(key)

    if key not in DEFAULT_SETTINGS:
        return await delete_setting(key)

    default_value = DEFAULT_SETTINGS[key]

    return await set_setting(
        key,
        default_value,
    )


async def reset_all_settings() -> None:
    """
    Reset all predefined Zara settings to their defaults.

    WARNING:
    This does not delete custom settings.
    """

    for key, value in DEFAULT_SETTINGS.items():

        if key == "updated_at":
            continue

        await set_setting(
            key,
            value,
        )


# ============================================================
# SETTINGS SNAPSHOT
# ============================================================

async def get_settings_snapshot() -> dict[str, Any]:
    """
    Return the important Zara runtime settings.
    """

    return {
        "access_mode": await get_access_mode(),

        "ai_enabled": await is_ai_enabled(),

        "voice_enabled": await is_voice_enabled(),

        "music_enabled": await is_music_enabled(),

        "maintenance_mode": (
            await is_maintenance_mode()
        ),

        "premium_stars": (
            await get_premium_price()
        ),

        "premium_duration_days": (
            await get_premium_duration_days()
        ),
    }


# ============================================================
# SETTINGS EXISTENCE
# ============================================================

async def setting_exists(
    key: str,
) -> bool:
    """
    Check whether a setting exists.
    """

    key = _validate_key(key)

    result = await settings_collection().find_one(
        {
            "key": key,
        },
        {
            "_id": 1,
        },
    )

    return result is not None
