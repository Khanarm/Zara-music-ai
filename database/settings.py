# database/settings.py

import logging
from typing import Any, Optional

from config import (
    AI_MAX_HISTORY,
    MAX_MEMORY_MESSAGES,
)

from database.mongodb import settings as settings_collection


logger = logging.getLogger(__name__)


# ============================================================
# DEFAULT SETTINGS
# ============================================================

DEFAULT_SETTINGS = {
    "ai_max_history": AI_MAX_HISTORY,
    "max_memory_messages": MAX_MEMORY_MESSAGES,
}


# ============================================================
# GET SETTING
# ============================================================

async def get_setting(
    key: str,
    default: Any = None,
) -> Any:
    """
    Get a setting from MongoDB.

    If the setting does not exist, return the supplied default.
    """

    try:
        document = await settings_collection().find_one(
            {"key": key}
        )

        if document is None:
            return default

        return document.get(
            "value",
            default,
        )

    except Exception:
        logger.exception(
            "Failed to get setting: %s",
            key,
        )

        return default


# ============================================================
# SET SETTING
# ============================================================

async def set_setting(
    key: str,
    value: Any,
) -> bool:
    """
    Create or update a setting.
    """

    try:
        await settings_collection().update_one(
            {"key": key},
            {
                "$set": {
                    "key": key,
                    "value": value,
                }
            },
            upsert=True,
        )

        return True

    except Exception:
        logger.exception(
            "Failed to save setting: %s",
            key,
        )

        return False


# ============================================================
# AI MAX HISTORY
# ============================================================

async def get_ai_max_history() -> int:
    """
    Return maximum AI conversation history.

    Config.py provides the default value.
    MongoDB can override it.
    """

    value = await get_setting(
        "ai_max_history",
        AI_MAX_HISTORY,
    )

    try:
        value = int(value)
    except (
        TypeError,
        ValueError,
    ):
        value = AI_MAX_HISTORY

    return max(
        1,
        value,
    )


async def set_ai_max_history(
    value: int,
) -> bool:
    """
    Update maximum AI conversation history.
    """

    try:
        value = max(
            1,
            int(value),
        )
    except (
        TypeError,
        ValueError,
    ):
        return False

    return await set_setting(
        "ai_max_history",
        value,
    )


# ============================================================
# MAX MEMORY MESSAGES
# ============================================================

async def get_max_memory_messages() -> int:
    """
    Return maximum stored memory messages.
    """

    value = await get_setting(
        "max_memory_messages",
        MAX_MEMORY_MESSAGES,
    )

    try:
        value = int(value)
    except (
        TypeError,
        ValueError,
    ):
        value = MAX_MEMORY_MESSAGES

    return max(
        1,
        value,
    )


async def set_max_memory_messages(
    value: int,
) -> bool:
    """
    Update maximum stored memory messages.
    """

    try:
        value = max(
            1,
            int(value),
        )
    except (
        TypeError,
        ValueError,
    ):
        return False

    return await set_setting(
        "max_memory_messages",
        value,
    )


# ============================================================
# INITIALIZE DEFAULT SETTINGS
# ============================================================

async def initialize_settings() -> None:
    """
    Create default settings if they don't exist.
    """

    for key, value in DEFAULT_SETTINGS.items():
        existing = await settings_collection().find_one(
            {"key": key}
        )

        if existing is None:
            await settings_collection().insert_one(
                {
                    "key": key,
                    "value": value,
                }
            )

            logger.info(
                "Created default setting: %s=%s",
                key,
                value,
            )


# ============================================================
# GET ALL SETTINGS
# ============================================================

async def get_all_settings() -> dict:
    """
    Return all application settings.
    """

    cursor = settings_collection().find({})

    documents = await cursor.to_list(
        length=None
    )

    result = {}

    for document in documents:
        key = document.get("key")

        if key:
            result[key] = document.get(
                "value"
            )

    return result
