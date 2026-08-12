# Zara AI — Telegram Voice Chat AI & Music Assistant

Zara is a conversational voice AI and music assistant built for Telegram Voice Chats, powered by Google Gemini, Telethon, PyTgCalls, and Aiogram 3.

## Features
- Natural Voice Chat Conversations (Hindi, Hinglish, English)
- Aaru Music Integration
- Telegram Stars (XTR) Subscription Management
- MongoDB Persistence & Robust Background Scheduler
- Railway / Docker Ready


## Part 1 — Zara VC Music

Part 1 only contains the VC music/video system. AI Talk and payment are not part of this release.

Flow:
`VC voice -> PyTgCalls incoming frames -> Gemini STT -> music intent -> YouTube search -> yt-dlp -> FIFO requester queue -> PyTgCalls MediaStream`.

### Voice controls
- `/join` — Zara joins an active group VC and starts listening.
- `/end` — Zara leaves the VC and clears music.
- `/use` — owner chooses All User or Admin request mode.

Music requests are spoken inside the VC. The current requester or a group admin/owner can control the current track.

### Dependencies
The reference playback stack is pinned to `py-tgcalls==2.0.6`. YouTube search uses `youtube-search-python` and media extraction/download uses `yt-dlp`. FFmpeg must be installed on the deployment host.

Set `STT_PROVIDER=gemini` and provide `GEMINI_API_KEY` for voice transcription.
