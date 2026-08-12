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

from pytgcalls import filters
from pytgcalls.types import AudioQuality, Device, Direction, RecordStream, StreamFrames

logger = logging.getLogger(__name__)


@dataclass
class SpeechBuffer:
    chunks: list[bytes] = field(default_factory=list)
    started_at: float = 0.0
    last_voice_at: float = 0.0
    bytes_count: int = 0


class VoiceChatReceiver:
    """Captures incoming Telegram VC microphone frames and sends complete utterances to STT."""

    SAMPLE_RATE = 48000
    CHANNELS = 2
    SAMPLE_WIDTH = 2
    FRAME_SECONDS = 0.02
    SILENCE_SECONDS = 0.75
    MIN_SPEECH_SECONDS = 0.55
    MAX_SPEECH_SECONDS = 8.0
    RMS_THRESHOLD = 450.0

    def __init__(self, calls, user_client, *, on_transcript: Callable[[int, int, str], Awaitable[None]]):
        self.calls = calls
        self.user_client = user_client
        self.on_transcript = on_transcript
        self.buffers: dict[tuple[int, int], SpeechBuffer] = {}
        self.active_chats: set[int] = set()
        self._registered = False
        self._tasks: set[asyncio.Task] = set()

    async def register(self) -> None:
        if self._registered:
            return

        @self.calls.on_update(
            filters.stream_frame(Direction.INCOMING, Device.MICROPHONE)
        )
        async def _frame_handler(_: object, update: StreamFrames):
            await self._handle_frames(update)

        self._registered = True

    async def join(self, chat_id: int) -> bool:
        await self.register()
        try:
            await self.calls.record(
                int(chat_id),
                RecordStream(True, AudioQuality.HIGH),
            )
            self.active_chats.add(int(chat_id))
            return True
        except Exception:
            logger.exception("Could not start VC receiver in %s", chat_id)
            return False

    async def leave(self, chat_id: int) -> None:
        chat_id = int(chat_id)
        self.active_chats.discard(chat_id)
        for key in [k for k in self.buffers if k[0] == chat_id]:
            self.buffers.pop(key, None)

    @staticmethod
    def _rms(data: bytes) -> float:
        if len(data) < 2:
            return 0.0
        count = len(data) // 2
        samples = struct.unpack(f"<{count}h", data[:count * 2])
        mean = sum(x * x for x in samples) / max(1, len(samples))
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

    async def _handle_frames(self, update: StreamFrames) -> None:
        chat_id = int(update.chat_id)
        if chat_id not in self.active_chats:
            return
        now = time.monotonic()
        for frame in update.frames:
            ssrc = int(getattr(frame, "ssrc", 0))
            data = bytes(getattr(frame, "frame", b""))
            if not data or not ssrc:
                continue
            key = (chat_id, ssrc)
            buf = self.buffers.setdefault(key, SpeechBuffer())
            voice = self._rms(data) >= self.RMS_THRESHOLD
            if voice:
                if not buf.chunks:
                    buf.started_at = now
                buf.last_voice_at = now
                buf.chunks.append(data)
                buf.bytes_count += len(data)
            elif buf.chunks:
                buf.chunks.append(data)
                buf.bytes_count += len(data)
                if now - buf.last_voice_at >= self.SILENCE_SECONDS:
                    await self._flush(chat_id, ssrc, buf)
                    self.buffers.pop(key, None)
            if buf.chunks and now - buf.started_at >= self.MAX_SPEECH_SECONDS:
                await self._flush(chat_id, ssrc, buf)
                self.buffers.pop(key, None)

    async def _resolve_user(self, chat_id: int, ssrc: int) -> Optional[int]:
        try:
            participants = await self.calls.get_participants(chat_id)
        except Exception:
            return None
        for participant in participants or []:
            source = getattr(participant, "source", None)
            if source is not None and int(source) == ssrc:
                return int(participant.user_id)
            for attr in ("video_info", "presentation_info"):
                info = getattr(participant, attr, None)
                for group in getattr(info, "sources", []) or []:
                    for value in getattr(group, "sources", []) or []:
                        if int(value) & 0xFFFFFFFF == ssrc & 0xFFFFFFFF:
                            return int(participant.user_id)
        return None

    async def _flush(self, chat_id: int, ssrc: int, buf: SpeechBuffer) -> None:
        if not buf.chunks:
            return
        duration = buf.bytes_count / (self.SAMPLE_RATE * self.CHANNELS * self.SAMPLE_WIDTH)
        if duration < self.MIN_SPEECH_SECONDS:
            return
        user_id = await self._resolve_user(chat_id, ssrc)
        if not user_id:
            logger.debug("Could not map VC SSRC %s to a Telegram user in %s", ssrc, chat_id)
            return
        pcm = b"".join(buf.chunks)
        path = Path(gettempdir()) / f"zara_vc_{chat_id}_{ssrc}_{int(time.time()*1000)}.wav"
        try:
            path.write_bytes(self._wav(pcm))
            task = asyncio.create_task(self._transcribe_and_dispatch(chat_id, user_id, path))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except Exception:
            logger.exception("Failed writing VC speech buffer")

    async def _transcribe_and_dispatch(self, chat_id: int, user_id: int, path: Path) -> None:
        try:
            from voice.stt import transcribe
            result = await transcribe(path, language="hi")
            text = result.text.strip()
            if text:
                logger.info("VC speech chat=%s user=%s: %s", chat_id, user_id, text)
                await self.on_transcript(chat_id, user_id, text)
        except Exception:
            logger.exception("VC speech transcription failed")
        finally:
            path.unlink(missing_ok=True)

    async def cleanup(self) -> None:
        self.active_chats.clear()
        self.buffers.clear()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()


__all__ = ["VoiceChatReceiver"]
