import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Track:
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


QUEUE: dict[int, list[Track]] = {}


def _chat_id(chat_id: int) -> int:
    return int(chat_id)


def _get_queue(
    chat_id: int,
    create: bool = True,
) -> list[Track]:

    chat_id = _chat_id(chat_id)

    if create:
        return QUEUE.setdefault(chat_id, [])

    return QUEUE.get(chat_id, [])


def add_to_queue(
    chat_id: int,
    track: Track,
) -> int:

    if not isinstance(track, Track):
        raise TypeError(
            "track must be a Track instance."
        )

    queue = _get_queue(chat_id)

    queue.append(track)

    position = len(queue)

    logger.info(
        "Added track: chat=%s position=%s title=%s user=%s",
        chat_id,
        position,
        track.title,
        track.requested_by,
    )

    return position


def add_track(
    chat_id: int,
    track: dict[str, Any],
) -> int:

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
        media_type=track.get(
            "media_type",
            "audio",
        ),
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


def get_next(
    chat_id: int,
) -> Optional[Track]:

    queue = _get_queue(
        chat_id,
        create=False,
    )

    if not queue:
        return None

    return queue[0]


def pop_next(
    chat_id: int,
) -> Optional[Track]:

    chat_id = _chat_id(chat_id)

    queue = _get_queue(
        chat_id,
        create=False,
    )

    if not queue:
        return None

    track = queue.pop(0)

    if not queue:
        QUEUE.pop(chat_id, None)

    logger.info(
        "Popped track: chat=%s title=%s",
        chat_id,
        track.title,
    )

    return track


def remove_from_queue(
    chat_id: int,
    index: int,
) -> Optional[Track]:

    chat_id = _chat_id(chat_id)

    queue = _get_queue(
        chat_id,
        create=False,
    )

    if not queue:
        return None

    try:
        index = int(index)
    except (TypeError, ValueError):
        return None

    if index < 0 or index >= len(queue):
        return None

    track = queue.pop(index)

    if not queue:
        QUEUE.pop(chat_id, None)

    return track


def remove_user_track(
    chat_id: int,
    user_id: int,
) -> Optional[Track]:

    chat_id = _chat_id(chat_id)
    user_id = int(user_id)

    queue = _get_queue(
        chat_id,
        create=False,
    )

    for index, track in enumerate(queue):

        if track.requested_by == user_id:

            removed = queue.pop(index)

            if not queue:
                QUEUE.pop(
                    chat_id,
                    None,
                )

            logger.info(
                "Removed user's track: chat=%s user=%s title=%s",
                chat_id,
                user_id,
                removed.title,
            )

            return removed

    return None


def remove_user_tracks(
    chat_id: int,
    user_id: int,
) -> int:

    chat_id = _chat_id(chat_id)
    user_id = int(user_id)

    queue = _get_queue(
        chat_id,
        create=False,
    )

    if not queue:
        return 0

    old = len(queue)

    queue[:] = [
        track
        for track in queue
        if track.requested_by != user_id
    ]

    removed = old - len(queue)

    if not queue:
        QUEUE.pop(chat_id, None)

    return removed


def clear_queue(
    chat_id: int,
) -> int:

    chat_id = _chat_id(chat_id)

    queue = QUEUE.pop(
        chat_id,
        [],
    )

    return len(queue)


def queue_size(
    chat_id: int,
) -> int:

    return len(
        _get_queue(
            chat_id,
            create=False,
        )
    )


def is_queue_empty(
    chat_id: int,
) -> bool:

    return queue_size(chat_id) == 0


def get_queue(
    chat_id: int,
) -> list[Track]:

    return list(
        _get_queue(
            chat_id,
            create=False,
        )
    )


def get_queue_dict(
    chat_id: int,
) -> list[dict[str, Any]]:

    return [
        track.to_dict()
        for track in get_queue(chat_id)
    ]


def get_track(
    chat_id: int,
    index: int,
) -> Optional[Track]:

    queue = _get_queue(
        chat_id,
        create=False,
    )

    try:
        index = int(index)
    except (TypeError, ValueError):
        return None

    if index < 0 or index >= len(queue):
        return None

    return queue[index]


def move_track(
    chat_id: int,
    from_index: int,
    to_index: int,
) -> bool:

    queue = _get_queue(
        chat_id,
        create=False,
    )

    try:
        from_index = int(from_index)
        to_index = int(to_index)
    except (TypeError, ValueError):
        return False

    if (
        from_index < 0
        or from_index >= len(queue)
        or to_index < 0
        or to_index >= len(queue)
    ):
        return False

    track = queue.pop(from_index)

    queue.insert(
        to_index,
        track,
    )

    return True


def swap_tracks(
    chat_id: int,
    first_index: int,
    second_index: int,
) -> bool:

    queue = _get_queue(
        chat_id,
        create=False,
    )

    try:
        first_index = int(first_index)
        second_index = int(second_index)
    except (TypeError, ValueError):
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


def find_track(
    chat_id: int,
    query: str,
) -> Optional[int]:

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


def get_queue_snapshot(
    chat_id: int,
) -> dict[str, Any]:

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


def clear_all_queues() -> int:

    count = len(QUEUE)

    QUEUE.clear()

    return count


def queue_exists(
    chat_id: int,
) -> bool:

    return _chat_id(chat_id) in QUEUE


__all__ = [
    "Track",
    "QUEUE",
    "add_to_queue",
    "add_track",
    "get_next",
    "pop_next",
    "remove_from_queue",
    "remove_user_track",
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
