"""
Telegram update handlers.

Incoming message types handled:
  - Text messages
  - Voice notes
  - Photos (including album groups — caption only on first photo)
  - /start command

All handlers check the user allowlist first; unknown users are ignored.
"""

import logging
import os

from telegram import Update
from telegram.ext import ContextTypes

import session
import storage

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
        "I'll assemble them into a draft post after an hour of inactivity."
    )


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
