"""
Telegram update handlers.

Incoming message types handled:
  - Text messages
  - Voice notes
  - Photos (including album groups — caption only on first photo)
  - /start command
  - /done command — immediately triggers processing without waiting for the timer
  - /status command — shows what's currently queued

All handlers check the user allowlist first; unknown users are ignored.
"""

import logging
import os
import time
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

import session
import storage

# Callback set by main.py so /done can fire processing directly
_process_callback = None


def set_process_callback(cb) -> None:
    global _process_callback
    _process_callback = cb

logger = logging.getLogger(__name__)

_ALLOWED_IDS: set[int] = set()


def configure_allowlist(raw: str) -> None:
    """Parse TELEGRAM_ALLOWED_USER_IDS env var into a set of ints."""
    global _ALLOWED_IDS
    _ALLOWED_IDS = {int(uid.strip()) for uid in raw.split(",") if uid.strip()}
    logger.info("Allowlist: %s", _ALLOWED_IDS)


def _allowed(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return uid in _ALLOWED_IDS


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text(
        "Ready. Send text, voice notes, or photos. "
        "I'll assemble them into a draft post after an hour of inactivity.\n\n"
        "/status — see what's queued\n"
        "/done — process immediately"
    )


async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    user_id = update.effective_user.id

    messages = await storage.get_messages(user_id)
    if not messages:
        await update.message.reply_text("Nothing queued yet.")
        return

    session.cancel(user_id)
    await update.message.reply_text(
        f"Processing {len(messages)} item(s) now — I'll let you know when the draft is committed."
    )
    if _process_callback:
        import asyncio
        asyncio.ensure_future(_process_callback(user_id))


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    user_id = update.effective_user.id
    messages = await storage.get_messages(user_id)

    if not messages:
        await update.message.reply_text("Nothing queued.")
        return

    counts = {"text": 0, "voice": 0, "photo": 0}
    for m in messages:
        counts[m["type"]] = counts.get(m["type"], 0) + 1

    first_ts = datetime.fromtimestamp(messages[0]["timestamp"], tz=timezone.utc).strftime("%H:%M UTC")
    last_ts = datetime.fromtimestamp(messages[-1]["timestamp"], tz=timezone.utc).strftime("%H:%M UTC")

    timeout = int(os.getenv("GROUPING_TIMEOUT_SECONDS", "3600"))
    fires_in = int((messages[-1]["timestamp"] + timeout) - time.time())
    fires_in = max(0, fires_in)
    mins, secs = divmod(fires_in, 60)

    lines = [f"*{len(messages)} item(s) queued* ({first_ts} – {last_ts})"]
    if counts["text"]:
        lines.append(f"  • {counts['text']} text message(s)")
    if counts["voice"]:
        lines.append(f"  • {counts['voice']} voice note(s)")
    if counts["photo"]:
        lines.append(f"  • {counts['photo']} photo(s)")
    lines.append(f"\nAuto-processes in {mins}m {secs}s — or send /done to go now.")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    user_id = update.effective_user.id
    text = update.message.text or ""

    await storage.add_message(user_id, "text", content=text)
    await session.touch(user_id)
    await update.message.reply_text("Got it.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    user_id = update.effective_user.id
    voice = update.message.voice

    # Check size before queuing
    if voice.file_size and voice.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "Voice note is over 20 MB — too large to process. Please send a shorter clip."
        )
        return

    # Count existing voice messages to generate a unique filename
    existing = await storage.get_messages(user_id)
    voice_count = sum(1 for m in existing if m["type"] == "voice") + 1
    filename = f"voice-{voice_count:02d}.ogg"

    await storage.add_message(
        user_id,
        "voice",
        file_id=voice.file_id,
        filename=filename,
    )
    await session.touch(user_id)
    await update.message.reply_text("Voice note queued.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    user_id = update.effective_user.id

    # Use the highest-resolution version
    photo = update.message.photo[-1]
    caption = update.message.caption or ""

    # Count existing photos
    existing = await storage.get_messages(user_id)
    photo_count = sum(1 for m in existing if m["type"] == "photo") + 1
    filename = f"image-{photo_count:02d}.jpg"

    # If there's a caption on the photo, store it as a preceding text message
    if caption:
        await storage.add_message(user_id, "text", content=caption)

    await storage.add_message(
        user_id,
        "photo",
        file_id=photo.file_id,
        filename=filename,
    )
    await session.touch(user_id)
    await update.message.reply_text("Photo queued.")
