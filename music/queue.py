# music/queue.py

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


logger = logging.getLogger(__name__)


# ============================================================
# TIME HELPER
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# TRACK MODEL
# ============================================================

@dataclass
class Track:
    """
    Represents one music track in Zara's queue.
    """

    title: str
    url: Optional[str] = None
    audio_url: Optional[str] = None
    audio_path: Optional[str] = None

    duration: Optional[int] = None

    requested_by: Optional[int] = None
    requested_by_name: Optional[str] = None

    thumbnail: Optional[str] = None
    source: Optional[str] = None
    media_type: str = "audio"

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    added_at: datetime = field(
        default_factory=utc_now
    )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert track to a dictionary.
        """

        return {
            "title": self.title,
            "url": self.url,
            "audio_url": self.audio_url,
            "audio_path": self.audio_path,
            "duration": self.duration,
            "requested_by": self.requested_by,
            "requested_by_name": self.requested_by_name,
            "thumbnail": self.thumbnail,
            "source": self.source,
            "media_type": self.media_type,
            "metadata": dict(self.metadata),
            "added_at": self.added_at,
        }


# ============================================================
# QUEUE STORAGE
# ============================================================

QUEUE: dict[int, list[Track]] = {}


# ============================================================
# INTERNAL HELPERS
# ============================================================

def _chat_id(chat_id: int) -> int:
    return int(chat_id)


def _get_queue(
    chat_id: int,
    create: bool = True,
) -> list[Track]:
    """
    Return the queue for a chat.
    """

    chat_id = _chat_id(chat_id)

    if create:
        return QUEUE.setdefault(
            chat_id,
            [],
        )

    return QUEUE.get(
        chat_id,
        [],
    )


# ============================================================
# ADD TRACK
# ============================================================

def add_to_queue(
    chat_id: int,
    track: Track,
) -> int:
    """
    Add a track to the end of the queue.

    Returns:
        Position of the added track.
    """

    if not isinstance(track, Track):
        raise TypeError(
            "track must be a Track instance."
        )

    queue = _get_queue(chat_id)

    queue.append(track)

    position = len(queue)

    logger.info(
        "Added track to queue: chat=%s position=%s title=%s",
        chat_id,
        position,
        track.title,
    )

    return position


# ============================================================
# ADD FROM DICTIONARY
# ============================================================

def add_track(
    chat_id: int,
    track: dict[str, Any],
) -> int:
    """
    Add a track using a dictionary.

    Useful for search/download modules.
    """

    if not isinstance(track, dict):
        raise TypeError(
            "track must be a dictionary."
        )

    item = Track(
        title=str(
            track.get(
                "title",
                "Unknown Track",
            )
        ),
        url=track.get("url"),
        audio_url=track.get("audio_url"),
        audio_path=track.get("audio_path"),
        duration=track.get("duration"),
        requested_by=track.get("requested_by"),
        requested_by_name=track.get(
            "requested_by_name"
        ),
        thumbnail=track.get("thumbnail"),
        source=track.get("source"),
        media_type=track.get("media_type", "audio"),
        metadata=dict(
            track.get(
                "metadata",
                {},
            )
        ),
    )

    return add_to_queue(
        chat_id,
        item,
    )


# ============================================================
# GET NEXT TRACK
# ============================================================

def get_next(
    chat_id: int,
) -> Optional[Track]:
    """
    Return the next queued track without removing it.
    """

    queue = _get_queue(
        chat_id,
        create=False,
    )

    if not queue:
        return None

    return queue[0]


# ============================================================
# POP NEXT TRACK
# ============================================================

def pop_next(
    chat_id: int,
) -> Optional[Track]:
    """
    Remove and return the first queued track.
    """

    chat_id = _chat_id(chat_id)

    queue = _get_queue(
        chat_id,
        create=False,
    )

    if not queue:
        return None

    track = queue.pop(0)

    if not queue:
        QUEUE.pop(
            chat_id,
            None,
        )

    logger.info(
        "Removed next track from queue: chat=%s title=%s",
        chat_id,
        track.title,
    )

    return track


# ============================================================
# REMOVE TRACK
# ============================================================

def remove_from_queue(
    chat_id: int,
    index: int,
) -> Optional[Track]:
    """
    Remove a track by zero-based index.

    Example:
        index=0 -> first track
        index=1 -> second track
    """

    queue = _get_queue(
        chat_id,
        create=False,
    )

    if not queue:
        return None

    try:
        index = int(index)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if index < 0 or index >= len(queue):
        return None

    track = queue.pop(index)

    if not queue:
        QUEUE.pop(
            _chat_id(chat_id),
            None,
        )

    logger.info(
        "Removed track from queue: chat=%s index=%s title=%s",
        chat_id,
        index,
        track.title,
    )

    return track


# ============================================================
# CLEAR QUEUE
# ============================================================

def clear_queue(
    chat_id: int,
) -> int:
    """
    Clear the entire queue.

    Returns:
        Number of tracks removed.
    """

    chat_id = _chat_id(chat_id)

    queue = QUEUE.pop(
        chat_id,
        [],
    )

    count = len(queue)

    if count:
        logger.info(
            "Cleared queue: chat=%s tracks=%s",
            chat_id,
            count,
        )

    return count


# ============================================================
# QUEUE SIZE
# ============================================================

def queue_size(
    chat_id: int,
) -> int:
    """
    Return number of queued tracks.
    """

    return len(
        _get_queue(
            chat_id,
            create=False,
        )
    )


# ============================================================
# IS EMPTY
# ============================================================

def is_queue_empty(
    chat_id: int,
) -> bool:
    """
    Check whether the queue is empty.
    """

    return queue_size(
        chat_id
    ) == 0


# ============================================================
# GET ALL TRACKS
# ============================================================

def get_queue(
    chat_id: int,
) -> list[Track]:
    """
    Return a copy of the current queue.

    The original internal list cannot be modified
    accidentally by the caller.
    """

    return list(
        _get_queue(
            chat_id,
            create=False,
        )
    )


# ============================================================
# QUEUE AS DICTIONARIES
# ============================================================

def get_queue_dict(
    chat_id: int,
) -> list[dict[str, Any]]:
    """
    Return queue tracks as dictionaries.
    """

    return [
        track.to_dict()
        for track in get_queue(chat_id)
    ]


# ============================================================
# GET TRACK BY INDEX
# ============================================================

def get_track(
    chat_id: int,
    index: int,
) -> Optional[Track]:
    """
    Get a queued track by zero-based index.
    """

    queue = _get_queue(
        chat_id,
        create=False,
    )

    try:
        index = int(index)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if index < 0 or index >= len(queue):
        return None

    return queue[index]


# ============================================================
# MOVE TRACK
# ============================================================

def move_track(
    chat_id: int,
    from_index: int,
    to_index: int,
) -> bool:
    """
    Move a track to another queue position.
    """

    queue = _get_queue(
        chat_id,
        create=False,
    )

    try:
        from_index = int(from_index)
        to_index = int(to_index)
    except (
        TypeError,
        ValueError,
    ):
        return False

    if (
        from_index < 0
        or from_index >= len(queue)
        or to_index < 0
        or to_index >= len(queue)
    ):
        return False

    track = queue.pop(
        from_index
    )

    queue.insert(
        to_index,
        track,
    )

    return True


# ============================================================
# SWAP TRACKS
# ============================================================

def swap_tracks(
    chat_id: int,
    first_index: int,
    second_index: int,
) -> bool:
    """
    Swap two queue positions.
    """

    queue = _get_queue(
        chat_id,
        create=False,
    )

    try:
        first_index = int(first_index)
        second_index = int(second_index)
    except (
        TypeError,
        ValueError,
    ):
        return False

    if (
        first_index < 0
        or second_index < 0
        or first_index >= len(queue)
        or second_index >= len(queue)
    ):
        return False

    queue[first_index], queue[second_index] = (
        queue[second_index],
        queue[first_index],
    )

    return True


# ============================================================
# REMOVE USER TRACKS
# ============================================================

def remove_user_tracks(
    chat_id: int,
    user_id: int,
) -> int:
    """
    Remove all tracks requested by a specific user.

    Returns:
        Number of removed tracks.
    """

    chat_id = _chat_id(chat_id)
    user_id = int(user_id)

    queue = _get_queue(
        chat_id,
        create=False,
    )

    if not queue:
        return 0

    original_count = len(queue)

    queue[:] = [
        track
        for track in queue
        if track.requested_by != user_id
    ]

    removed = (
        original_count
        - len(queue)
    )

    if not queue:
        QUEUE.pop(
            chat_id,
            None,
        )

    if removed:
        logger.info(
            "Removed user tracks: chat=%s user=%s count=%s",
            chat_id,
            user_id,
            removed,
        )

    return removed


# ============================================================
# SEARCH QUEUE
# ============================================================

def find_track(
    chat_id: int,
    query: str,
) -> Optional[int]:
    """
    Find the first queued track matching a title.

    Returns:
        Zero-based index or None.
    """

    query = str(
        query or ""
    ).strip().lower()

    if not query:
        return None

    queue = _get_queue(
        chat_id,
        create=False,
    )

    for index, track in enumerate(queue):
        if query in track.title.lower():
            return index

    return None


# ============================================================
# QUEUE SNAPSHOT
# ============================================================

def get_queue_snapshot(
    chat_id: int,
) -> dict[str, Any]:
    """
    Return a useful queue snapshot for player/control modules.
    """

    queue = get_queue(chat_id)

    return {
        "chat_id": int(chat_id),
        "size": len(queue),
        "tracks": [
            track.to_dict()
            for track in queue
        ],
        "updated_at": utc_now(),
    }


# ============================================================
# REMOVE ALL QUEUES
# ============================================================

def clear_all_queues() -> int:
    """
    Clear queues for every chat.

    Returns:
        Number of chats cleared.
    """

    count = len(QUEUE)

    QUEUE.clear()

    if count:
        logger.info(
            "Cleared all music queues: chats=%s",
            count,
        )

    return count


# ============================================================
# QUEUE EXISTS
# ============================================================

def queue_exists(
    chat_id: int,
) -> bool:
    """
    Check whether a chat currently has a queue.
    """

    return _chat_id(chat_id) in QUEUE


# ============================================================
# EXPORT
# ============================================================

__all__ = [
    "Track",
    "QUEUE",
    "add_to_queue",
    "add_track",
    "get_next",
    "pop_next",
    "remove_from_queue",
    "clear_queue",
    "queue_size",
    "is_queue_empty",
    "get_queue",
    "get_queue_dict",
    "get_track",
    "move_track",
    "swap_tracks",
    "remove_user_tracks",
    "find_track",
    "get_queue_snapshot",
    "clear_all_queues",
    "queue_exists",
]
