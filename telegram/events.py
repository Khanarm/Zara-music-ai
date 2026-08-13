async def handle_music_intent(
    message: Message,
    intent: str,
) -> bool:

    if not message.from_user:
        return False

    if not message.chat:
        return False

    try:

        (
            player,
            downloader,
            searcher,
            controls,
        ) = await _music_services()

        chat_id = message.chat.id
        user_id = message.from_user.id

        text = clean_message_text(
            message
        )

        # ====================================================
        # DELETE MUSIC REQUEST MESSAGE
        # ====================================================

        async def delete_request():
            try:
                await message.delete()
            except Exception:
                pass

        # ====================================================
        # SKIP
        # ====================================================

        if intent == MUSIC_SKIP:

            is_admin = await _group_admin(
                message.bot,
                chat_id,
                user_id,
            )

            result = await controls.skip_for_user(
                chat_id,
                user_id,
                is_admin=is_admin,
            )

            await delete_request()

            if result == "current":
                await message.answer(
                    "⏭️ Song skipped."
                )
                return True

            if result == "queued":
                await message.answer(
                    "⏭️ Tumhara queued song skip ho gaya."
                )
                return True

            if result == "stopped":
                await message.answer(
                    "⏹️ Queue empty hai."
                )
                return True

            if result == "denied":
                await message.answer(
                    "⛔ Tum sirf apna song skip kar sakte ho."
                )
                return True

            await message.answer(
                "📭 Music queue empty hai."
            )

            return True

        # ====================================================
        # PLAY / SEARCH
        # ====================================================

        if intent in (
            MUSIC_SEARCH,
            MUSIC_PLAY,
        ):

            # ------------------------------------------------
            # Processing FIRST
            # ------------------------------------------------

            processing = await message.answer(
                "🎵 Processing..."
            )

            await delete_request()

            # ------------------------------------------------
            # Query
            # ------------------------------------------------

            query = text

            prefixes = (
                "search song",
                "song search",
                "gana search",
                "gaana search",
                "music search",
                "find song",
                "find music",
                "search music",
                "vplay",
                "play",
                "chalao",
                "chala",
                "bajao",
                "baja do",
                "song chala",
                "gana chala",
                "gaana chala",
            )

            lowered = query.lower()

            requested_video = (
                lowered.startswith(
                    "vplay"
                )
            )

            for prefix in prefixes:

                if lowered.startswith(
                    prefix
                ):

                    query = query[
                        len(prefix):
                    ].strip(
                        " :-"
                    )

                    break

            if not query:

                try:
                    await processing.edit_text(
                        "🎵 Song ka naam batao."
                    )
                except Exception:
                    pass

                return True

            # ------------------------------------------------
            # SEARCH
            # ------------------------------------------------

            result = await searcher.first(
                query
            )

            if not result:

                try:
                    await processing.edit_text(
                        "❌ Song nahi mila."
                    )
                except Exception:
                    pass

                return True

            # ------------------------------------------------
            # DOWNLOAD
            # ------------------------------------------------

            path = await downloader.download(
                result,
                video=requested_video,
            )

            if not path:

                try:
                    await processing.edit_text(
                        "❌ Song download nahi ho paya."
                    )
                except Exception:
                    pass

                return True

            # ------------------------------------------------
            # TRACK
            # ------------------------------------------------

            from music.queue import Track

            metadata = dict(
                getattr(
                    result,
                    "metadata",
                    {},
                ) or {}
            )

            metadata[
                "telegram_message"
            ] = None

            track = Track(
                title=result.title,
                url=result.url,
                audio_url=result.url,
                audio_path=path,
                duration=result.duration,
                requested_by=user_id,
                requested_by_name=(
                    message.from_user.full_name
                ),
                source=result.source,
                media_type=(
                    "video"
                    if requested_video
                    else "audio"
                ),
                metadata=metadata,
            )

            # ------------------------------------------------
            # QUEUE LIMIT
            # ------------------------------------------------

            max_queue = 10

            try:

                from config import (
                    MUSIC_MAX_QUEUE,
                )

                max_queue = int(
                    MUSIC_MAX_QUEUE
                )

            except Exception:
                pass

            # Current song is not counted.
            if (
                player.queue_size(chat_id)
                >= max_queue
            ):

                await downloader.delete(
                    path
                )

                try:
                    await processing.edit_text(
                        "⚠️ Queue full hai."
                    )
                except Exception:
                    pass

                return True

            # ------------------------------------------------
            # VC JOIN
            # ------------------------------------------------

            try:

                from telegram.client import (
                    get_voice_music_services,
                )

                receiver, _ = (
                    get_voice_music_services()
                )

                if not receiver.is_joined(
                    chat_id
                ):

                    joined = await receiver.join(
                        chat_id
                    )

                    if not joined:

                        await downloader.delete(
                            path
                        )

                        try:
                            await processing.edit_text(
                                "❌ Active Voice Chat nahi mila."
                            )
                        except Exception:
                            pass

                        return True

            except Exception:

                logger.exception(
                    "Automatic VC join failed."
                )

                await downloader.delete(
                    path
                )

                try:
                    await processing.edit_text(
                        "❌ Zara VC join nahi kar paayi."
                    )
                except Exception:
                    pass

                return True

            # ------------------------------------------------
            # ADD QUEUE
            # ------------------------------------------------

            position = await player.add(
                chat_id,
                track,
                play_now=(
                    not player.is_playing(
                        chat_id
                    )
                    and player.current(
                        chat_id
                    ) is None
                ),
            )

            # ------------------------------------------------
            # PROCESSING MESSAGE
            # ------------------------------------------------

            try:

                await processing.edit_text(
                    (
                        "🎵 <b>Processing...</b>\n"
                        f"🎶 <b>{result.title}</b>\n"
                        f"👤 {message.from_user.full_name}"
                    )
                )

            except Exception:
                pass

            # ------------------------------------------------
            # SONG INFORMATION
            # ------------------------------------------------

            # If this song became current, post info now.
            current = player.current(
                chat_id
            )

            if current is track:

                try:

                    await message.bot.send_message(
                        chat_id,
                        (
                            "🎵 <b>Play by Zara Music</b>\n\n"
                            f"🎶 <b>{track.title}</b>\n"
                            f"👤 <b>Requested by:</b> "
                            f"{track.requested_by_name}"
                        ),
                    )

                except Exception:

                    logger.exception(
                        "Song info message failed."
                    )

            else:

                # Queue message
                try:

                    await message.bot.send_message(
                        chat_id,
                        (
                            "🎵 <b>Added to Queue</b>\n\n"
                            f"🎶 <b>{track.title}</b>\n"
                            f"📌 Position: <b>{position}</b>\n"
                            f"👤 <b>Requested by:</b> "
                            f"{track.requested_by_name}"
                        ),
                    )

                except Exception:
                    pass

            return True

        # ====================================================
        # OTHER MUSIC COMMANDS
        # ====================================================

        if intent == MUSIC_PAUSE:

            ok = await controls.pause(
                chat_id
            )

            await delete_request()

            await message.answer(
                "⏸️ Paused."
                if ok
                else
                "⚠️ Pause is not supported."
            )

            return True

        if intent == MUSIC_RESUME:

            ok = await controls.resume(
                chat_id
            )

            await delete_request()

            await message.answer(
                "▶️ Resumed."
                if ok
                else
                "❌ Nothing to resume."
            )

            return True

        if intent == MUSIC_STOP:

            await controls.stop(
                chat_id,
                True,
            )

            await delete_request()

            await message.answer(
                "⏹️ Music stopped and queue cleared."
            )

            return True

        if intent == MUSIC_QUEUE:

            q = controls.queue(
                chat_id
            )

            await delete_request()

            if not q:

                await message.answer(
                    "📭 Queue empty hai."
                )

                return True

            lines = [
                "🎵 <b>Queue</b>"
            ]

            for i, track in enumerate(
                q,
                1,
            ):

                lines.append(
                    f"{i}. {track.title} "
                    f"— {track.requested_by_name or 'Unknown'}"
                )

            await message.answer(
                "\n".join(lines[:31])
            )

            return True

        if intent == MUSIC_REMOVE:

            q = controls.queue(
                chat_id
            )

            await delete_request()

            if not q:

                await message.answer(
                    "📭 Queue empty hai."
                )

                return True

            # Remove first queued song.
            removed = controls.remove(
                chat_id,
                0,
            )

            if removed:

                await downloader.delete(
                    removed.audio_path
                )

            await message.answer(
                (
                    f"🗑️ Removed: "
                    f"<b>{removed.title}</b>"
                )
                if removed
                else
                "❌ Song remove nahi hua."
            )

            return True

    except Exception:

        logger.exception(
            "Music handler failed."
        )

        try:

            await message.answer(
                "❌ Music system me error aa gaya."
            )

        except Exception:
            pass

        return True

    return False
