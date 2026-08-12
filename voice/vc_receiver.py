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
    Telegram VC incoming-audio receiver.

    This module intentionally does not import old PyTgCalls classes such as
    Device, Direction, RecordStream or StreamFrames at module import time.
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

        self.buffers: dict[tuple[int, int], SpeechBuffer] = {}
        self.active_chats: set[int] = set()

        self._registered = False
        self._tasks: set[asyncio.Task] = set()

    async def register(self) -> None:
        """
        Register incoming stream-frame listener when supported by the
        installed PyTgCalls version.

        Older/newer PyTgCalls versions expose different frame APIs, so this
        method avoids crashing the whole Telegram bot during import.
        """

        if self._registered:
            return

        try:
            from pytgcalls import filters

            on_update = getattr(self.calls, "on_update", None)

            if on_update is None:
                logger.warning(
                    "Installed PyTgCalls does not expose on_update(); "
                    "VC speech receiver frame capture is unavailable."
                )
                self._registered = True
                return

            stream_filter = filters.stream_frame()

            @self.calls.on_update(stream_filter)
            async def _frame_handler(_, update):
                await self._handle_frames(update)

            self._registered = True

            logger.info(
                "VoiceChatReceiver stream-frame handler registered."
            )

        except Exception:
            logger.exception(
                "Could not register VC stream-frame receiver."
            )

            # Do not crash Zara just because optional speech reception
            # is unavailable.
            self._registered = True

    async def join(self, chat_id: int) -> bool:
        """
        Enable incoming VC audio capture.

        The actual recording/start mechanism depends on the installed
        PyTgCalls API. We try the available method without importing
        deprecated classes.
        """

        chat_id = int(chat_id)

        await self.register()

        try:
            record = getattr(self.calls, "record", None)

            if record is None:
                logger.warning(
                    "PyTgCalls record() API is unavailable for VC receiver."
                )
                return False

            # Try the modern/simple record interface first.
            try:
                await record(chat_id)
            except TypeError:
                logger.warning(
                    "PyTgCalls record() requires a stream object; "
                    "incoming VC speech receiver is unavailable with "
                    "the currently installed API."
                )
                return False

            self.active_chats.add(chat_id)

            logger.info(
                "VC speech receiver joined chat %s",
                chat_id,
            )

            return True

        except Exception:
            logger.exception(
                "Could not start VC receiver in %s",
                chat_id,
            )
            return False

    async def leave(self, chat_id: int) -> None:
        chat_id = int(chat_id)

        self.active_chats.discard(chat_id)

        for key in list(self.buffers):
            if key[0] == chat_id:
                self.buffers.pop(key, None)

        logger.info(
            "VC speech receiver left chat %s",
            chat_id,
        )

    @staticmethod
    def _rms(data: bytes) -> float:
        if not data:
            return 0.0

        usable_length = len(data) - (len(data) % 2)

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

        mean = sum(
            sample * sample
            for sample in samples
        ) / max(1, len(samples))

        return mean ** 0.5

    @classmethod
    def _wav(cls, pcm: bytes) -> bytes:
        output = io.BytesIO()

        with wave.open(output, "wb") as wav:
            wav.setnchannels(cls.CHANNELS)
            wav.setsampwidth(cls.SAMPLE_WIDTH)
            wav.setframerate(cls.SAMPLE_RATE)
            wav.writeframes(pcm)

        return output.getvalue()

    async def _handle_frames(self, update) -> None:
        """
        Process incoming StreamFrames-like objects.

        This intentionally uses attribute access instead of importing
        StreamFrames so the code remains compatible with different
        PyTgCalls releases.
        """

        chat_id = getattr(update, "chat_id", None)

        if chat_id is None:
            return

        chat_id = int(chat_id)

        if chat_id not in self.active_chats:
            return

        frames = getattr(update, "frames", None)

        if not frames:
            return

        now = time.monotonic()

        for frame in frames:
            ssrc = int(
                getattr(frame, "ssrc", 0) or 0
            )

            data = getattr(frame, "frame", b"")

            if not data:
                continue

            try:
                data = bytes(data)
            except Exception:
                continue

            if not ssrc:
                continue

            key = (chat_id, ssrc)

            buf = self.buffers.setdefault(
                key,
                SpeechBuffer(),
            )

            voice = (
                self._rms(data)
                >= self.RMS_THRESHOLD
            )

            if voice:
                if not buf.chunks:
                    buf.started_at = now

                buf.last_voice_at = now

                buf.chunks.append(data)
                buf.bytes_count += len(data)

            elif buf.chunks:
                buf.chunks.append(data)
                buf.bytes_count += len(data)

                if (
                    now - buf.last_voice_at
                    >= self.SILENCE_SECONDS
                ):
                    await self._flush(
                        chat_id,
                        ssrc,
                        buf,
                    )

                    self.buffers.pop(
                        key,
                        None,
                    )

            if (
                buf.chunks
                and now - buf.started_at
                >= self.MAX_SPEECH_SECONDS
            ):
                await self._flush(
                    chat_id,
                    ssrc,
                    buf,
                )

                self.buffers.pop(
                    key,
                    None,
                )

    async def _resolve_user(
        self,
        chat_id: int,
        ssrc: int,
    ) -> Optional[int]:
        """
        Try to map an audio SSRC to a Telegram user.

        Different PyTgCalls versions expose participants differently,
        therefore this function fails safely.
        """

        try:
            get_participants = getattr(
                self.calls,
                "get_participants",
                None,
            )

            if get_participants is None:
                return None

            participants = await get_participants(
                chat_id
            )

        except Exception:
            return None

        for participant in participants or []:
            source = getattr(
                participant,
                "source",
                None,
            )

            if source is not None:
                try:
                    if int(source) == ssrc:
                        user_id = getattr(
                            participant,
                            "user_id",
                            None,
                        )

                        if user_id:
                            return int(user_id)

                except Exception:
                    pass

            for attr in (
                "video_info",
                "presentation_info",
            ):
                info = getattr(
                    participant,
                    attr,
                    None,
                )

                if not info:
                    continue

                for group in (
                    getattr(info, "sources", [])
                    or []
                ):
                    for value in (
                        getattr(group, "sources", [])
                        or []
                    ):
                        try:
                            if (
                                int(value)
                                & 0xFFFFFFFF
                            ) == (
                                ssrc
                                & 0xFFFFFFFF
                            ):
                                user_id = getattr(
                                    participant,
                                    "user_id",
                                    None,
                                )

                                if user_id:
                                    return int(user_id)

                        except Exception:
                            continue

        return None

    async def _flush(
        self,
        chat_id: int,
        ssrc: int,
        buf: SpeechBuffer,
    ) -> None:

        if not buf.chunks:
            return

        bytes_per_second = (
            self.SAMPLE_RATE
            * self.CHANNELS
            * self.SAMPLE_WIDTH
        )

        duration = (
            buf.bytes_count
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
                "Could not map VC SSRC %s to Telegram user in %s",
                ssrc,
                chat_id,
            )
            return

        pcm = b"".join(buf.chunks)

        path = (
            Path(gettempdir())
            / (
                f"zara_vc_"
                f"{chat_id}_"
                f"{ssrc}_"
                f"{int(time.time() * 1000)}.wav"
            )
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

            self._tasks.add(task)

            task.add_done_callback(
                self._tasks.discard
            )

        except Exception:
            logger.exception(
                "Failed writing VC speech buffer."
            )

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

            text = str(text).strip()

            if text:
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

    async def cleanup(self) -> None:
        self.active_chats.clear()
        self.buffers.clear()

        if self._tasks:
            await asyncio.gather(
                *self._tasks,
                return_exceptions=True,
            )

        self._tasks.clear()


__all__ = ["VoiceChatReceiver"]
