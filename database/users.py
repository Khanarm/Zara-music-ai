# database/users.py

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database.mongodb import users as users_collection

logger = logging.getLogger(__name__)


# ============================================================
# TIME HELPERS
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# USER DOCUMENT
# ============================================================

def build_user_document(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    language_code: Optional[str] = None,
) -> dict[str, Any]:
    """
    Build a new Zara user document.
    """

    now = utc_now()

    return {
        "user_id": int(user_id),
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "language_code": language_code,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
        "is_active": True,
        "is_blocked": False,
    }


# ============================================================
# CREATE / UPDATE USER
# ============================================================

async def create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    language_code: Optional[str] = None,
) -> dict[str, Any]:
    """
    Create a Zara user if the user does not already exist.

    If the user already exists, update the latest Telegram
    profile information and last-seen timestamp.
    """

    user_id = int(user_id)
    now = utc_now()

    existing = await users_collection().find_one(
        {"user_id": user_id}
    )

    if existing:
        await users_collection().update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "language_code": language_code,
                    "updated_at": now,
                    "last_seen_at": now,
                }
            },
        )

        updated = await get_user(user_id)

        if updated is None:
            raise RuntimeError(
                "User disappeared after update."
            )

        return updated

    document = build_user_document(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        language_code=language_code,
    )

    await users_collection().insert_one(
        document
    )

    logger.info(
        "Created Zara user: %s",
        user_id,
    )

    return document


# ============================================================
# GET USER
# ============================================================

async def get_user(
    user_id: int,
) -> Optional[dict[str, Any]]:
    """
    Get a user by Telegram user ID.
    """

    return await users_collection().find_one(
        {"user_id": int(user_id)}
    )


# ============================================================
# GET OR CREATE USER
# ============================================================

async def get_or_create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    language_code: Optional[str] = None,
) -> dict[str, Any]:
    """
    Return an existing user or create a new one.
    """

    user = await get_user(user_id)

    if user is not None:
        now = utc_now()

        await users_collection().update_one(
            {"user_id": int(user_id)},
            {
                "$set": {
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "language_code": language_code,
                    "updated_at": now,
                    "last_seen_at": now,
                }
            },
        )

        updated = await get_user(user_id)

        if updated is not None:
            return updated

        return user

    return await create_user(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        language_code=language_code,
    )


# ============================================================
# UPDATE USER
# ============================================================

async def update_user(
    user_id: int,
    updates: dict[str, Any],
) -> bool:
    """
    Update allowed user fields.

    Internal database fields such as _id and user_id cannot
    be changed through this helper.
    """

    if not updates:
        return False

    protected_fields = {
        "_id",
        "user_id",
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

    result = await users_collection().update_one(
        {"user_id": int(user_id)},
        {
            "$set": clean_updates,
        },
    )

    return result.modified_count > 0


# ============================================================
# LAST SEEN
# ============================================================

async def update_last_seen(
    user_id: int,
) -> bool:
    """
    Update the user's last-seen timestamp.
    """

    result = await users_collection().update_one(
        {"user_id": int(user_id)},
        {
            "$set": {
                "last_seen_at": utc_now(),
                "updated_at": utc_now(),
            }
        },
    )

    return result.modified_count > 0


# ============================================================
# BLOCK USER
# ============================================================

async def block_user(
    user_id: int,
    reason: Optional[str] = None,
) -> bool:
    """
    Block a user.

    Blocking is separate from subscription/access mode.
    """

    update: dict[str, Any] = {
        "is_blocked": True,
        "is_active": False,
        "blocked_at": utc_now(),
        "updated_at": utc_now(),
    }

    if reason:
        update["blocked_reason"] = reason

    result = await users_collection().update_one(
        {"user_id": int(user_id)},
        {
            "$set": update,
        },
    )

    return result.modified_count > 0


# ============================================================
# UNBLOCK USER
# ============================================================

async def unblock_user(
    user_id: int,
) -> bool:
    """
    Unblock a user.
    """

    result = await users_collection().update_one(
        {"user_id": int(user_id)},
        {
            "$set": {
                "is_blocked": False,
                "is_active": True,
                "updated_at": utc_now(),
            },
            "$unset": {
                "blocked_at": "",
                "blocked_reason": "",
            },
        },
    )

    return result.modified_count > 0


# ============================================================
# ACTIVE STATUS
# ============================================================

async def set_user_active(
    user_id: int,
    active: bool,
) -> bool:
    """
    Enable or disable a user account.
    """

    result = await users_collection().update_one(
        {"user_id": int(user_id)},
        {
            "$set": {
                "is_active": bool(active),
                "updated_at": utc_now(),
            }
        },
    )

    return result.modified_count > 0


# ============================================================
# BLOCK STATUS
# ============================================================

async def is_user_blocked(
    user_id: int,
) -> bool:
    """
    Return True if the user is blocked.
    """

    user = await get_user(user_id)

    if not user:
        return False

    return bool(
        user.get("is_blocked", False)
    )


# ============================================================
# ACTIVE CHECK
# ============================================================

async def is_user_active(
    user_id: int,
) -> bool:
    """
    Return True if the user exists and is active.
    """

    user = await get_user(user_id)

    if not user:
        return False

    if user.get("is_blocked", False):
        return False

    return bool(
        user.get("is_active", True)
    )


# ============================================================
# USERNAME LOOKUP
# ============================================================

async def get_user_by_username(
    username: str,
) -> Optional[dict[str, Any]]:
    """
    Find a user by username.

    Username is normalized without @.
    """

    username = username.strip()

    if username.startswith("@"):
        username = username[1:]

    if not username:
        return None

    return await users_collection().find_one(
        {
            "username": username,
        }
    )


# ============================================================
# USER LANGUAGE
# ============================================================

async def set_language(
    user_id: int,
    language_code: str,
) -> bool:
    """
    Save the user's preferred language.
    """

    language_code = (
        language_code.strip()
        if language_code
        else ""
    )

    if not language_code:
        return False

    result = await users_collection().update_one(
        {"user_id": int(user_id)},
        {
            "$set": {
                "language_code": language_code,
                "updated_at": utc_now(),
            }
        },
    )

    return result.modified_count > 0


async def get_language(
    user_id: int,
    default: str = "en",
) -> str:
    """
    Get user's preferred language.
    """

    user = await get_user(user_id)

    if not user:
        return default

    return user.get(
        "language_code",
        default,
    ) or default


# ============================================================
# AI SETTINGS
# ============================================================

async def set_ai_enabled(
    user_id: int,
    enabled: bool,
) -> bool:
    """
    Enable or disable AI interaction for a user.
    """

    result = await users_collection().update_one(
        {"user_id": int(user_id)},
        {
            "$set": {
                "ai_enabled": bool(enabled),
                "updated_at": utc_now(),
            }
        },
    )

    return result.modified_count > 0


async def is_ai_enabled(
    user_id: int,
) -> bool:
    """
    Return whether AI is enabled for the user.

    New users are considered enabled by default.
    """

    user = await get_user(user_id)

    if not user:
        return True

    return bool(
        user.get(
            "ai_enabled",
            True,
        )
    )


# ============================================================
# USER PREFERENCES
# ============================================================

async def set_preference(
    user_id: int,
    key: str,
    value: Any,
) -> bool:
    """
    Store a user preference.

    Preferences are namespaced under:
        preferences.<key>
    """

    key = key.strip()

    if not key:
        return False

    if key.startswith("$") or "." in key:
        raise ValueError(
            "Invalid preference key."
        )

    result = await users_collection().update_one(
        {"user_id": int(user_id)},
        {
            "$set": {
                f"preferences.{key}": value,
                "updated_at": utc_now(),
            }
        },
    )

    return result.modified_count > 0


async def get_preference(
    user_id: int,
    key: str,
    default: Any = None,
) -> Any:
    """
    Get a user preference.
    """

    key = key.strip()

    if not key:
        return default

    user = await get_user(user_id)

    if not user:
        return default

    preferences = user.get(
        "preferences",
        {},
    )

    return preferences.get(
        key,
        default,
    )


# ============================================================
# USER STATS
# ============================================================

async def increment_stat(
    user_id: int,
    stat_name: str,
    amount: int = 1,
) -> bool:
    """
    Increment a numeric user statistic.

    Example:
        voice_messages
        ai_messages
        music_requests
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

    result = await users_collection().update_one(
        {"user_id": int(user_id)},
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
# USER DELETE
# ============================================================

async def delete_user(
    user_id: int,
) -> bool:
    """
    Delete a user document.

    IMPORTANT:
    Related subscriptions/payments/memory should be handled
    by their respective modules before permanent deletion.
    """

    result = await users_collection().delete_one(
        {"user_id": int(user_id)}
    )

    if result.deleted_count:
        logger.info(
            "Deleted Zara user: %s",
            user_id,
        )

        return True

    return False


# ============================================================
# USER COUNT
# ============================================================

async def count_users(
    active_only: bool = False,
) -> int:
    """
    Count Zara users.
    """

    query: dict[str, Any] = {}

    if active_only:
        query["is_active"] = True
        query["is_blocked"] = False

    return await users_collection().count_documents(
        query
    )


# ============================================================
# USER EXISTS
# ============================================================

async def user_exists(
    user_id: int,
) -> bool:
    """
    Check whether a user exists.
    """

    user = await users_collection().find_one(
        {
            "user_id": int(user_id),
        },
        {
            "_id": 1,
        },
    )

    return user is not None
