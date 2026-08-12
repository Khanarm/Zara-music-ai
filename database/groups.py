# database/groups.py

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database.mongodb import groups as groups_collection

logger = logging.getLogger(__name__)


# ============================================================
# TIME HELPER
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# GROUP DOCUMENT
# ============================================================

def build_group_document(
    chat_id: int,
    title: Optional[str] = None,
    username: Optional[str] = None,
    group_type: str = "group",
) -> dict[str, Any]:
    """
    Build a new Zara group document.
    """

    now = utc_now()

    return {
        "chat_id": int(chat_id),
        "title": title,
        "username": username,
        "group_type": group_type,

        "enabled": True,
        "bot_available": True,
        "zara_active": False,

        "voice_chat_active": False,
        "voice_chat_joined": False,

        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,

        "bot_removed": False,
        "bot_removed_at": None,

        "settings": {
            "voice_enabled": True,
            "music_enabled": True,
            "ai_enabled": True,
        },

        "stats": {
            "voice_requests": 0,
            "ai_requests": 0,
            "music_requests": 0,
        },
    }


# ============================================================
# CREATE GROUP
# ============================================================

async def create_group(
    chat_id: int,
    title: Optional[str] = None,
    username: Optional[str] = None,
    group_type: str = "group",
) -> dict[str, Any]:
    """
    Create a group if it does not exist.

    Existing groups are updated with latest Telegram
    information.
    """

    chat_id = int(chat_id)
    now = utc_now()

    existing = await get_group(chat_id)

    if existing:
        await groups_collection().update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "title": title,
                    "username": username,
                    "group_type": group_type,
                    "last_seen_at": now,
                    "updated_at": now,
                }
            },
        )

        updated = await get_group(chat_id)

        if updated is not None:
            return updated

        return existing

    document = build_group_document(
        chat_id=chat_id,
        title=title,
        username=username,
        group_type=group_type,
    )

    await groups_collection().insert_one(
        document
    )

    logger.info(
        "Created Zara group: %s",
        chat_id,
    )

    return document


# ============================================================
# GET GROUP
# ============================================================

async def get_group(
    chat_id: int,
) -> Optional[dict[str, Any]]:
    """
    Get a group by Telegram chat ID.
    """

    return await groups_collection().find_one(
        {
            "chat_id": int(chat_id),
        }
    )


# ============================================================
# GET OR CREATE GROUP
# ============================================================

async def get_or_create_group(
    chat_id: int,
    title: Optional[str] = None,
    username: Optional[str] = None,
    group_type: str = "group",
) -> dict[str, Any]:
    """
    Return an existing group or create it.
    """

    group = await get_group(chat_id)

    if group:
        now = utc_now()

        await groups_collection().update_one(
            {"chat_id": int(chat_id)},
            {
                "$set": {
                    "title": title,
                    "username": username,
                    "group_type": group_type,
                    "last_seen_at": now,
                    "updated_at": now,
                }
            },
        )

        updated = await get_group(chat_id)

        if updated is not None:
            return updated

        return group

    return await create_group(
        chat_id=chat_id,
        title=title,
        username=username,
        group_type=group_type,
    )


# ============================================================
# UPDATE GROUP
# ============================================================

async def update_group(
    chat_id: int,
    updates: dict[str, Any],
) -> bool:
    """
    Update group fields.

    chat_id and created_at cannot be changed.
    """

    if not updates:
        return False

    protected_fields = {
        "_id",
        "chat_id",
        "created_at",
    }

    clean_updates = {
        key: value
        for key, value in updates.items()
        if key not in protected_fields
    }

    if not clean_updates:
        return False

    clean_updates["updated_at"] = utc_now()

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": clean_updates,
        },
    )

    return result.modified_count > 0


# ============================================================
# GROUP TITLE
# ============================================================

async def update_group_info(
    chat_id: int,
    title: Optional[str] = None,
    username: Optional[str] = None,
    group_type: Optional[str] = None,
) -> bool:
    """
    Update Telegram group information.
    """

    updates: dict[str, Any] = {}

    if title is not None:
        updates["title"] = title

    if username is not None:
        updates["username"] = username

    if group_type is not None:
        updates["group_type"] = group_type

    if not updates:
        return False

    updates["last_seen_at"] = utc_now()

    return await update_group(
        chat_id,
        updates,
    )


# ============================================================
# ENABLE / DISABLE GROUP
# ============================================================

async def set_group_enabled(
    chat_id: int,
    enabled: bool,
) -> bool:
    """
    Enable or disable Zara for a group.
    """

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": {
                "enabled": bool(enabled),
                "updated_at": utc_now(),
            },
        },
    )

    return result.modified_count > 0


async def is_group_enabled(
    chat_id: int,
) -> bool:
    """
    Return whether the group is enabled.
    """

    group = await get_group(chat_id)

    if not group:
        return False

    return bool(
        group.get(
            "enabled",
            False,
        )
    )


# ============================================================
# BOT AVAILABILITY
# ============================================================

async def set_bot_available(
    chat_id: int,
    available: bool,
) -> bool:
    """
    Mark whether Manager Bot can currently access the group.
    """

    update: dict[str, Any] = {
        "bot_available": bool(available),
        "updated_at": utc_now(),
    }

    if available:
        update["bot_removed"] = False
        update["bot_removed_at"] = None
    else:
        update["bot_removed"] = True
        update["bot_removed_at"] = utc_now()

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": update,
        },
    )

    return result.modified_count > 0


async def is_bot_available(
    chat_id: int,
) -> bool:
    """
    Return whether the Manager Bot is available in the group.
    """

    group = await get_group(chat_id)

    if not group:
        return False

    return bool(
        group.get(
            "bot_available",
            False,
        )
    )


# ============================================================
# BOT REMOVED
# ============================================================

async def mark_bot_removed(
    chat_id: int,
) -> bool:
    """
    Mark a group unavailable because Manager Bot was removed.

    Payment/subscription records are intentionally NOT deleted.
    """

    now = utc_now()

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": {
                "bot_available": False,
                "bot_removed": True,
                "bot_removed_at": now,
                "zara_active": False,
                "voice_chat_active": False,
                "voice_chat_joined": False,
                "updated_at": now,
            },
        },
    )

    return result.modified_count > 0


# ============================================================
# BOT RESTORED
# ============================================================

async def mark_bot_restored(
    chat_id: int,
) -> bool:
    """
    Mark the Manager Bot as available again.
    """

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": {
                "bot_available": True,
                "bot_removed": False,
                "bot_removed_at": None,
                "updated_at": utc_now(),
            },
        },
    )

    return result.modified_count > 0


# ============================================================
# ZARA ACTIVE STATE
# ============================================================

async def set_zara_active(
    chat_id: int,
    active: bool,
) -> bool:
    """
    Mark whether Zara is currently active in the group.
    """

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": {
                "zara_active": bool(active),
                "updated_at": utc_now(),
            },
        },
    )

    return result.modified_count > 0


async def is_zara_active(
    chat_id: int,
) -> bool:
    """
    Return whether Zara is currently active.
    """

    group = await get_group(chat_id)

    if not group:
        return False

    return bool(
        group.get(
            "zara_active",
            False,
        )
    )


# ============================================================
# VOICE CHAT STATE
# ============================================================

async def set_voice_chat_state(
    chat_id: int,
    active: bool,
    joined: bool = False,
) -> bool:
    """
    Update Voice Chat state.
    """

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": {
                "voice_chat_active": bool(active),
                "voice_chat_joined": bool(joined),
                "updated_at": utc_now(),
            },
        },
    )

    return result.modified_count > 0


async def set_voice_chat_joined(
    chat_id: int,
    joined: bool,
) -> bool:
    """
    Update only Zara's Voice Chat joined state.
    """

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": {
                "voice_chat_joined": bool(joined),
                "updated_at": utc_now(),
            },
        },
    )

    return result.modified_count > 0


async def is_voice_chat_joined(
    chat_id: int,
) -> bool:
    """
    Return whether Zara is currently joined to the VC.
    """

    group = await get_group(chat_id)

    if not group:
        return False

    return bool(
        group.get(
            "voice_chat_joined",
            False,
        )
    )


# ============================================================
# GROUP SETTINGS
# ============================================================

async def set_group_setting(
    chat_id: int,
    key: str,
    value: Any,
) -> bool:
    """
    Store a group-specific Zara setting.

    Example:
        voice_enabled
        music_enabled
        ai_enabled
    """

    key = key.strip()

    if not key:
        return False

    if key.startswith("$") or "." in key:
        raise ValueError(
            "Invalid group setting key."
        )

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": {
                f"settings.{key}": value,
                "updated_at": utc_now(),
            },
        },
    )

    return result.modified_count > 0


async def get_group_setting(
    chat_id: int,
    key: str,
    default: Any = None,
) -> Any:
    """
    Get a group-specific setting.
    """

    group = await get_group(chat_id)

    if not group:
        return default

    settings = group.get(
        "settings",
        {},
    )

    return settings.get(
        key,
        default,
    )


# ============================================================
# FEATURE SETTINGS
# ============================================================

async def set_voice_enabled(
    chat_id: int,
    enabled: bool,
) -> bool:
    return await set_group_setting(
        chat_id,
        "voice_enabled",
        bool(enabled),
    )


async def is_voice_enabled(
    chat_id: int,
) -> bool:
    return bool(
        await get_group_setting(
            chat_id,
            "voice_enabled",
            True,
        )
    )


async def set_music_enabled(
    chat_id: int,
    enabled: bool,
) -> bool:
    return await set_group_setting(
        chat_id,
        "music_enabled",
        bool(enabled),
    )


async def is_music_enabled(
    chat_id: int,
) -> bool:
    return bool(
        await get_group_setting(
            chat_id,
            "music_enabled",
            True,
        )
    )


async def set_ai_enabled(
    chat_id: int,
    enabled: bool,
) -> bool:
    return await set_group_setting(
        chat_id,
        "ai_enabled",
        bool(enabled),
    )


async def is_ai_enabled(
    chat_id: int,
) -> bool:
    return bool(
        await get_group_setting(
            chat_id,
            "ai_enabled",
            True,
        )
    )


# ============================================================
# GROUP STATISTICS
# ============================================================

async def increment_stat(
    chat_id: int,
    stat_name: str,
    amount: int = 1,
) -> bool:
    """
    Increment a group statistic.
    """

    stat_name = stat_name.strip()

    if not stat_name:
        return False

    if (
        stat_name.startswith("$")
        or "." in stat_name
    ):
        raise ValueError(
            "Invalid statistic name."
        )

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$inc": {
                f"stats.{stat_name}": int(amount),
            },
            "$set": {
                "updated_at": utc_now(),
            },
        },
    )

    return result.modified_count > 0


# ============================================================
# GROUP ACCESS CHECK
# ============================================================

async def is_group_available(
    chat_id: int,
) -> bool:
    """
    Check whether Zara can operate in the group at the
    basic group-availability level.

    Subscription checks are handled separately.
    """

    group = await get_group(chat_id)

    if not group:
        return False

    if not group.get(
        "enabled",
        False,
    ):
        return False

    if not group.get(
        "bot_available",
        False,
    ):
        return False

    if group.get(
        "bot_removed",
        False,
    ):
        return False

    return True


# ============================================================
# GROUP LIST
# ============================================================

async def get_enabled_groups(
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Return enabled and available groups.
    """

    cursor = (
        groups_collection()
        .find(
            {
                "enabled": True,
                "bot_available": True,
                "bot_removed": False,
            }
        )
        .sort(
            "updated_at",
            -1,
        )
        .limit(limit)
    )

    return await cursor.to_list(
        length=limit
    )


async def get_all_groups(
    limit: int = 500,
) -> list[dict[str, Any]]:
    """
    Return groups known to Zara.
    """

    cursor = (
        groups_collection()
        .find({})
        .sort(
            "updated_at",
            -1,
        )
        .limit(limit)
    )

    return await cursor.to_list(
        length=limit
    )


# ============================================================
# GROUP COUNT
# ============================================================

async def count_groups(
    enabled_only: bool = False,
) -> int:
    """
    Count groups.
    """

    query: dict[str, Any] = {}

    if enabled_only:
        query = {
            "enabled": True,
            "bot_available": True,
            "bot_removed": False,
        }

    return await groups_collection().count_documents(
        query
    )


# ============================================================
# GROUP EXISTS
# ============================================================

async def group_exists(
    chat_id: int,
) -> bool:
    """
    Check whether a group exists in the database.
    """

    result = await groups_collection().find_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "_id": 1,
        },
    )

    return result is not None


# ============================================================
# DELETE GROUP
# ============================================================

async def delete_group(
    chat_id: int,
) -> bool:
    """
    Delete a group document.

    IMPORTANT:
    This does not delete subscriptions or payment history.
    Those must be handled by their own modules.
    """

    result = await groups_collection().delete_one(
        {
            "chat_id": int(chat_id),
        }
    )

    if result.deleted_count:
        logger.info(
            "Deleted Zara group: %s",
            chat_id,
        )

        return True

    return False


# ============================================================
# MARK GROUP SEEN
# ============================================================

async def mark_group_seen(
    chat_id: int,
) -> bool:
    """
    Update the last-seen timestamp.
    """

    now = utc_now()

    result = await groups_collection().update_one(
        {
            "chat_id": int(chat_id),
        },
        {
            "$set": {
                "last_seen_at": now,
                "updated_at": now,
            },
        },
    )

    return result.modified_count > 0
