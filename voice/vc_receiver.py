# voice/vc_receiver.py

import asyncio
import io
import logging
import struct
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import gettempdir
from typing import Awaitable, Callable, Optional


logger = logging.getLogger(__name__)


@dataclass
class SpeechBuffer:
    chunks: list[bytes] = field(default_factory=list)
    started_at: float = 0.0
    last_voice_at: float = 0.0
    bytes_count: int = 0


class VoiceChatReceiver:
    """
    Zara Telegram Voice Chat receiver.

    Important:
    The installed PyTgCalls version does not expose the old
    stream_frame / Device / Direction / RecordStream API.

    Therefore this class:
      - never imports deprecated PyTgCalls classes
      - never crashes Telegram startup because VC receiver is unavailable
      - keeps the receiver API compatible with telegram.client
      - supports frame processing if a compatible frame callback
        is available in the installed PyTgCalls version
    """

    SAMPLE_RATE = 48000
    CHANNELS = 2
    SAMPLE_WIDTH = 2

    SILENCE_SECONDS = 0.75
    MIN_SPEECH_SECONDS = 0.55
    MAX_SPEECH_SECONDS = 8.0
    RMS_THRESHOLD = 450.0

    def __init__(
        self,
        calls,
        user_client,
        *,
        on_transcript: Callable[
            [int, int, str],
            Awaitable[None],
        ],
    ):
        self.calls = calls
        self.user_client = user_client
        self.on_transcript = on_transcript

        self.buffers: dict[
            tuple[int, int],
            SpeechBuffer,
        ] = {}

        self.active_chats: set[int] = set()

        self._registered = False
        self._frame_capture_available = False

        self._tasks: set[asyncio.Task] = set()

    # ========================================================
    # REGISTER
    # ========================================================

    async def register(self) -> None:
        """
        Register a compatible frame callback if the installed
        PyTgCalls version supports one.

        The current PyTgCalls installation shown in the logs does
        NOT expose filters.stream_frame(), so registration is
        optional and must never break the bot.
        """

        if self._registered:
            return

        self._registered = True

        try:
            from pytgcalls import filters

            stream_frame = getattr(
                filters,
                "stream_frame",
                None,
            )

            on_update = getattr(
                self.calls,
                "on_update",
                None,
            )

            if stream_frame is None:
                logger.warning(
                    "PyTgCalls does not provide "
                    "filters.stream_frame(). "
                    "VC speech frame capture is unavailable."
                )
                return

            if on_update is None:
                logger.warning(
                    "PyTgCalls does not provide on_update(). "
                    "VC speech frame capture is unavailable."
                )
                return

            # Some versions expose stream_frame as a factory.
            # Some versions require arguments.
            try:
                stream_filter = stream_frame()
            except TypeError:
                logger.warning(
                    "Installed PyTgCalls stream_frame() API "
                    "requires arguments. VC speech capture disabled."
                )
                return

            @self.calls.on_update(stream_filter)
            async def _frame_handler(
                _,
                update,
            ):
                await self._handle_frames(update)

            self._frame_capture_available = True

            logger.info(
                "VC speech frame receiver registered successfully."
            )

        except Exception:
            self._frame_capture_available = False

            logger.exception(
                "VC speech frame receiver registration failed. "
                "Continuing without speech capture."
            )

    # ========================================================
    # JOIN
    # ========================================================

    async def join(
        self,
        chat_id: int,
    ) -> bool:
        """
        Mark a VC as active for speech receiving.

        We intentionally do NOT call the old PyTgCalls record()
        API because the installed version does not provide the
        compatible RecordStream interface.
        """

        chat_id = int(chat_id)

        await self.register()

        if not self._frame_capture_available:
            logger.warning(
                "VC receiver joined logically for %s, but incoming "
                "speech capture is unavailable with the installed "
                "PyTgCalls API.",
                chat_id,
            )

            # Do not pretend that audio capture is working.
            # Returning False allows caller to handle this safely.
            return False

        self.active_chats.add(chat_id)

        logger.info(
            "VC speech receiver activated for chat %s",
            chat_id,
        )

        return True

    # ========================================================
    # LEAVE
    # ========================================================

    async def leave(
        self,
        chat_id: int,
    ) -> None:

        chat_id = int(chat_id)

        self.active_chats.discard(chat_id)

        for key in list(self.buffers):
            if key[0] == chat_id:
                self.buffers.pop(key, None)

        logger.info(
            "VC speech receiver stopped for chat %s",
            chat_id,
        )

    # ========================================================
    # RMS
    # ========================================================

    @staticmethod
    def _rms(
        data: bytes,
    ) -> float:

        if not data:
            return 0.0

        usable_length = (
            len(data)
            - (len(data) % 2)
        )

        if usable_length <= 0:
            return 0.0

        count = usable_length // 2

        try:
            samples = struct.unpack(
                f"<{count}h",
                data[:usable_length],
            )
        except struct.error:
            return 0.0

        if not samples:
            return 0.0

        mean = sum(
            sample * sample
            for sample in samples
        ) / len(samples)

        return mean ** 0.5

    # ========================================================
    # WAV
    # ========================================================

    @classmethod
    def _wav(
        cls,
        pcm: bytes,
    ) -> bytes:

        output = io.BytesIO()

        with wave.open(
            output,
            "wb",
        ) as wav:

            wav.setnchannels(
                cls.CHANNELS
            )

            wav.setsampwidth(
                cls.SAMPLE_WIDTH
            )

            wav.setframerate(
                cls.SAMPLE_RATE
            )

            wav.writeframes(
                pcm
            )

        return output.getvalue()

    # ========================================================
    # FRAME HANDLER
    # ========================================================

    async def _handle_frames(
        self,
        update,
    ) -> None:

        chat_id = getattr(
            update,
            "chat_id",
            None,
        )

        if chat_id is None:
            return

        try:
            chat_id = int(chat_id)
        except Exception:
            return

        if chat_id not in self.active_chats:
            return

        frames = getattr(
            update,
            "frames",
            None,
        )

        if not frames:
            return

        now = time.monotonic()

        for frame in frames:

            ssrc = getattr(
                frame,
                "ssrc",
                0,
            )

            try:
                ssrc = int(ssrc or 0)
            except Exception:
                ssrc = 0

            if not ssrc:
                continue

            data = getattr(
                frame,
                "frame",
                None,
            )

            if not data:
                continue

            try:
                data = bytes(data)
            except Exception:
                continue

            key = (
                chat_id,
                ssrc,
            )

            buffer = self.buffers.setdefault(
                key,
                SpeechBuffer(),
            )

            voice_detected = (
                self._rms(data)
                >= self.RMS_THRESHOLD
            )

            # ------------------------------------------------
            # VOICE
            # ------------------------------------------------

            if voice_detected:

                if not buffer.chunks:
                    buffer.started_at = now

                buffer.last_voice_at = now

                buffer.chunks.append(
                    data
                )

                buffer.bytes_count += len(
                    data
                )

            # ------------------------------------------------
            # SILENCE
            # ------------------------------------------------

            elif buffer.chunks:

                buffer.chunks.append(
                    data
                )

                buffer.bytes_count += len(
                    data
                )

                if (
                    now
                    - buffer.last_voice_at
                    >= self.SILENCE_SECONDS
                ):

                    await self._flush(
                        chat_id,
                        ssrc,
                        buffer,
                    )

                    self.buffers.pop(
                        key,
                        None,
                    )

            # ------------------------------------------------
            # MAX SPEECH
            # ------------------------------------------------

            if (
                buffer.chunks
                and
                now
                - buffer.started_at
                >= self.MAX_SPEECH_SECONDS
            ):

                await self._flush(
                    chat_id,
                    ssrc,
                    buffer,
                )

                self.buffers.pop(
                    key,
                    None,
                )

    # ========================================================
    # RESOLVE USER
    # ========================================================

    async def _resolve_user(
        self,
        chat_id: int,
        ssrc: int,
    ) -> Optional[int]:

        get_participants = getattr(
            self.calls,
            "get_participants",
            None,
        )

        if get_participants is None:
            return None

        try:
            participants = await get_participants(
                chat_id
            )
        except Exception:
            return None

        for participant in (
            participants or []
        ):

            user_id = getattr(
                participant,
                "user_id",
                None,
            )

            if not user_id:
                continue

            # ------------------------------------------------
            # Direct source
            # ------------------------------------------------

            source = getattr(
                participant,
                "source",
                None,
            )

            if source is not None:

                try:
                    if int(source) == ssrc:
                        return int(user_id)
                except Exception:
                    pass

            # ------------------------------------------------
            # Video / presentation sources
            # ------------------------------------------------

            for attr in (
                "video_info",
                "presentation_info",
            ):

                info = getattr(
                    participant,
                    attr,
                    None,
                )

                if info is None:
                    continue

                groups = getattr(
                    info,
                    "sources",
                    None,
                )

                if not groups:
                    continue

                for group in groups:

                    values = getattr(
                        group,
                        "sources",
                        None,
                    )

                    if not values:
                        continue

                    for value in values:

                        try:
                            if (
                                int(value)
                                & 0xFFFFFFFF
                            ) == (
                                ssrc
                                & 0xFFFFFFFF
                            ):
                                return int(
                                    user_id
                                )

                        except Exception:
                            continue

        return None

    # ========================================================
    # FLUSH SPEECH
    # ========================================================

    async def _flush(
        self,
        chat_id: int,
        ssrc: int,
        buffer: SpeechBuffer,
    ) -> None:

        if not buffer.chunks:
            return

        bytes_per_second = (
            self.SAMPLE_RATE
            * self.CHANNELS
            * self.SAMPLE_WIDTH
        )

        duration = (
            buffer.bytes_count
            / bytes_per_second
        )

        if duration < self.MIN_SPEECH_SECONDS:
            return

        user_id = await self._resolve_user(
            chat_id,
            ssrc,
        )

        if not user_id:
            logger.debug(
                "Unable to map SSRC %s to Telegram user "
                "in chat %s.",
                ssrc,
                chat_id,
            )
            return

        pcm = b"".join(
            buffer.chunks
        )

        filename = (
            f"zara_vc_"
            f"{chat_id}_"
            f"{ssrc}_"
            f"{int(time.time() * 1000)}"
            f".wav"
        )

        path = (
            Path(gettempdir())
            / filename
        )

        try:

            path.write_bytes(
                self._wav(pcm)
            )

            task = asyncio.create_task(
                self._transcribe_and_dispatch(
                    chat_id,
                    user_id,
                    path,
                )
            )

            self._tasks.add(
                task
            )

            task.add_done_callback(
                self._tasks.discard
            )

        except Exception:
            logger.exception(
                "Failed creating VC speech WAV."
            )

    # ========================================================
    # TRANSCRIBE
    # ========================================================

    async def _transcribe_and_dispatch(
        self,
        chat_id: int,
        user_id: int,
        path: Path,
    ) -> None:

        try:

            from voice.stt import transcribe

            result = await transcribe(
                path,
                language="hi",
            )

            text = getattr(
                result,
                "text",
                "",
            )

            text = str(
                text
            ).strip()

            if not text:
                return

            logger.info(
                "VC speech chat=%s user=%s: %s",
                chat_id,
                user_id,
                text,
            )

            await self.on_transcript(
                chat_id,
                user_id,
                text,
            )

        except Exception:
            logger.exception(
                "VC speech transcription failed."
            )

        finally:

            try:
                path.unlink(
                    missing_ok=True
                )
            except Exception:
                pass

    # ========================================================
    # CLEANUP
    # ========================================================

    async def cleanup(self) -> None:

        self.active_chats.clear()
        self.buffers.clear()

        if self._tasks:

            await asyncio.gather(
                *self._tasks,
                return_exceptions=True,
            )

        self._tasks.clear()

        logger.info(
            "VoiceChatReceiver cleaned up."
        )


__all__ = [
    "VoiceChatReceiver",
]
