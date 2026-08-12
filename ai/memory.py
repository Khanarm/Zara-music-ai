# ai/memory.py

import logging
from datetime import datetime, timezone
from typing import Optional

from database.mongodb import memory as memory_collection
from database.settings import get_ai_max_history


logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_user_id(user_id: int) -> int:
    return int(user_id)


def normalize_chat_id(chat_id: int) -> int:
    return int(chat_id)


# ============================================================
# SAVE MESSAGE
# ============================================================

async def save_message(
    user_id: int,
    role: str,
    content: str,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None,
    username: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Save one conversation message.

    role:
        user
        assistant
        system
    """

    role = str(role).lower().strip()

    if role not in {
        "user",
        "assistant",
        "system",
    }:
        raise ValueError(
            "Invalid message role."
        )

    content = str(content).strip()

    if not content:
        return None

    document = {
        "user_id": normalize_user_id(user_id),
        "role": role,
        "content": content,
        "chat_id": (
            normalize_chat_id(chat_id)
            if chat_id is not None
            else None
        ),
        "message_id": message_id,
        "username": username,
        "metadata": metadata or {},
        "created_at": utc_now(),
    }

    result = await memory_collection().insert_one(
        document
    )

    document["_id"] = result.inserted_id

    return document


# ============================================================
# SAVE USER MESSAGE
# ============================================================

async def save_user_message(
    user_id: int,
    content: str,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None,
    username: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Save a user message.
    """

    return await save_message(
        user_id=user_id,
        role="user",
        content=content,
        chat_id=chat_id,
        message_id=message_id,
        username=username,
        metadata=metadata,
    )


# ============================================================
# SAVE ASSISTANT MESSAGE
# ============================================================

async def save_assistant_message(
    user_id: int,
    content: str,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Save Zara's response.
    """

    return await save_message(
        user_id=user_id,
        role="assistant",
        content=content,
        chat_id=chat_id,
        message_id=message_id,
        metadata=metadata,
    )


# ============================================================
# SAVE SYSTEM MESSAGE
# ============================================================

async def save_system_message(
    user_id: int,
    content: str,
    chat_id: Optional[int] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Save a system/context message.
    """

    return await save_message(
        user_id=user_id,
        role="system",
        content=content,
        chat_id=chat_id,
        metadata=metadata,
    )


# ============================================================
# GET HISTORY
# ============================================================

async def get_history(
    user_id: int,
    chat_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """
    Return recent conversation history.

    History is returned oldest -> newest,
    which is the natural order for AI context.
    """

    if limit is None:
        limit = await get_ai_max_history()

    limit = max(
        1,
        int(limit),
    )

    query = {
        "user_id": normalize_user_id(
            user_id
        ),
    }

    if chat_id is not None:
        query["chat_id"] = normalize_chat_id(
            chat_id
        )

    cursor = memory_collection().find(
        query
    ).sort(
        "created_at",
        -1,
    ).limit(limit)

    messages = await cursor.to_list(
        length=limit
    )

    messages.reverse()

    return messages


# ============================================================
# GET AI HISTORY
# ============================================================

async def get_ai_history(
    user_id: int,
    chat_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """
    Return only user/assistant messages.

    System messages are excluded because the AI system
    prompt is handled separately.
    """

    history = await get_history(
        user_id=user_id,
        chat_id=chat_id,
        limit=limit,
    )

    return [
        message
        for message in history
        if message.get("role")
        in {
            "user",
            "assistant",
        }
    ]


# ============================================================
# GEMINI-FRIENDLY HISTORY
# ============================================================

async def get_formatted_history(
    user_id: int,
    chat_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """
    Return conversation history in a simple format
    suitable for building Gemini context.
    """

    history = await get_ai_history(
        user_id=user_id,
        chat_id=chat_id,
        limit=limit,
    )

    formatted = []

    for message in history:
        role = message.get(
            "role"
        )

        content = message.get(
            "content",
            "",
        )

        if not content:
            continue

        formatted.append(
            {
                "role": role,
                "content": content,
            }
        )

    return formatted


# ============================================================
# GET LAST MESSAGE
# ============================================================

async def get_last_message(
    user_id: int,
    chat_id: Optional[int] = None,
) -> Optional[dict]:
    """
    Return the latest conversation message.
    """

    query = {
        "user_id": normalize_user_id(
            user_id
        ),
    }

    if chat_id is not None:
        query["chat_id"] = normalize_chat_id(
            chat_id
        )

    return await memory_collection().find_one(
        query,
        sort=[
            (
                "created_at",
                -1,
            )
        ],
    )


# ============================================================
# CLEAR HISTORY
# ============================================================

async def clear_history(
    user_id: int,
    chat_id: Optional[int] = None,
) -> int:
    """
    Delete conversation history.

    If chat_id is supplied, only that chat's
    history is deleted.
    """

    query = {
        "user_id": normalize_user_id(
            user_id
        ),
    }

    if chat_id is not None:
        query["chat_id"] = normalize_chat_id(
            chat_id
        )

    result = await memory_collection().delete_many(
        query
    )

    deleted = result.deleted_count

    logger.info(
        "Cleared %s memory messages for user %s",
        deleted,
        user_id,
    )

    return deleted


# ============================================================
# TRIM HISTORY
# ============================================================

async def trim_history(
    user_id: int,
    chat_id: Optional[int] = None,
    keep: Optional[int] = None,
) -> int:
    """
    Keep only the newest N messages.

    Returns the number of deleted messages.
    """

    if keep is None:
        keep = await get_ai_max_history()

    keep = max(
        1,
        int(keep),
    )

    query = {
        "user_id": normalize_user_id(
            user_id
        ),
    }

    if chat_id is not None:
        query["chat_id"] = normalize_chat_id(
            chat_id
        )

    cursor = memory_collection().find(
        query,
        {
            "_id": 1,
        },
    ).sort(
        "created_at",
        -1,
    ).skip(keep)

    old_messages = await cursor.to_list(
        length=None
    )

    if not old_messages:
        return 0

    ids = [
        message["_id"]
        for message in old_messages
    ]

    result = await memory_collection().delete_many(
        {
            "_id": {
                "$in": ids,
            }
        }
    )

    return result.deleted_count


# ============================================================
# SAVE + TRIM
# ============================================================

async def save_and_trim(
    user_id: int,
    role: str,
    content: str,
    chat_id: Optional[int] = None,
    message_id: Optional[int] = None,
    username: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Save message and automatically trim old history.
    """

    message = await save_message(
        user_id=user_id,
        role=role,
        content=content,
        chat_id=chat_id,
        message_id=message_id,
        username=username,
        metadata=metadata,
    )

    if message:
        try:
            await trim_history(
                user_id=user_id,
                chat_id=chat_id,
            )
        except Exception:
            logger.exception(
                "Failed to trim memory for user %s",
                user_id,
            )

    return message


# ============================================================
# MESSAGE COUNT
# ============================================================

async def count_messages(
    user_id: int,
    chat_id: Optional[int] = None,
) -> int:
    """
    Count stored memory messages.
    """

    query = {
        "user_id": normalize_user_id(
            user_id
        ),
    }

    if chat_id is not None:
        query["chat_id"] = normalize_chat_id(
            chat_id
        )

    return await memory_collection().count_documents(
        query
    )


async def count_user_messages(
    user_id: int,
    chat_id: Optional[int] = None,
) -> int:
    """
    Count only user messages.
    """

    query = {
        "user_id": normalize_user_id(
            user_id
        ),
        "role": "user",
    }

    if chat_id is not None:
        query["chat_id"] = normalize_chat_id(
            chat_id
        )

    return await memory_collection().count_documents(
        query
    )


# ============================================================
# SEARCH MEMORY
# ============================================================

async def search_memory(
    user_id: int,
    query_text: str,
    chat_id: Optional[int] = None,
    limit: int = 10,
) -> list[dict]:
    """
    Simple text search in user's stored memory.

    This uses MongoDB regex search.
    Later this can be upgraded to vector/semantic memory.
    """

    query_text = str(
        query_text
    ).strip()

    if not query_text:
        return []

    query = {
        "user_id": normalize_user_id(
            user_id
        ),
        "content": {
            "$regex": query_text,
            "$options": "i",
        },
    }

    if chat_id is not None:
        query["chat_id"] = normalize_chat_id(
            chat_id
        )

    cursor = memory_collection().find(
        query
    ).sort(
        "created_at",
        -1,
    ).limit(limit)

    return await cursor.to_list(
        length=limit
    )


# ============================================================
# DELETE OLD MEMORY
# ============================================================

async def delete_old_memory(
    days: int = 30,
    limit: int = 1000,
) -> int:
    """
    Delete memory older than the specified number of days.

    This can be called by the scheduler.
    """

    from datetime import timedelta

    days = max(
        1,
        int(days),
    )

    cutoff = (
        utc_now()
        - timedelta(days=days)
    )

    old_messages = await memory_collection().find(
        {
            "created_at": {
                "$lt": cutoff,
            }
        },
        {
            "_id": 1,
        },
    ).limit(limit).to_list(
        length=limit
    )

    if not old_messages:
        return 0

    ids = [
        message["_id"]
        for message in old_messages
    ]

    result = await memory_collection().delete_many(
        {
            "_id": {
                "$in": ids,
            }
        }
    )

    logger.info(
        "Deleted %s old AI memory messages.",
        result.deleted_count,
    )

    return result.deleted_count
