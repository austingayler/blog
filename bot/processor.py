"""
Processing pipeline: runs when a session's sliding window expires.

Steps:
  1. Load all buffered messages from SQLite
  2. Download any voice/photo files that haven't been downloaded yet
  3. Transcribe voice notes via Whisper API
  4. Build chronological event log
  5. Call GPT-4o to generate draft markdown
  6. Commit post.md + images to GitHub via Git Data API
  7. Clean up session from SQLite
"""

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from openai import AsyncOpenAI
from telegram import Bot

import github_client
import storage
from prompts import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB — Telegram Bot API download limit


def _openai() -> AsyncOpenAI:
    """Lazy client — instantiated on first call so the key is read at runtime."""
    return AsyncOpenAI()


async def run(user_id: int, bot: Bot) -> None:
    """Entry point called by the session timer."""
    logger.info("Processing session for user %s", user_id)

    try:
        await storage.mark_processing(user_id)
        messages = await storage.get_messages(user_id)

        if not messages:
            logger.info("No messages for user %s — skipping", user_id)
            await storage.delete_session(user_id)
            return

        data_dir = os.environ.get("DATA_DIR", "./data")
        session_dir = Path(data_dir) / "files" / str(user_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        # --- Step 1: Download files & transcribe voice ---
        images: list[tuple[str, bytes]] = []  # (filename, raw_bytes)

        for msg in messages:
            if msg["type"] in ("voice", "photo") and msg["file_id"]:
                local_path = session_dir / msg["filename"]

                if not local_path.exists():
                    raw = await _download_file(bot, msg["file_id"])
                    if raw is None:
                        continue
                    local_path.write_bytes(raw)

                if msg["type"] == "voice" and not msg["content"]:
                    transcript = await _transcribe(local_path)
                    await storage.update_message_content(msg["id"], transcript)
                    msg["content"] = transcript

                if msg["type"] == "photo":
                    images.append((msg["filename"], local_path.read_bytes()))

        # Reload messages so transcripts are fresh
        messages = await storage.get_messages(user_id)

        # --- Step 2: Build event log for GPT-4o ---
        events = []
        for msg in messages:
            ts = datetime.fromtimestamp(msg["timestamp"], tz=timezone.utc).strftime(
                "%H:%M:%S"
            )
            if msg["type"] == "photo":
                events.append({"type": "photo", "timestamp": ts, "content": msg["filename"]})
            elif msg["type"] == "voice":
                events.append({"type": "voice", "timestamp": ts, "content": msg["content"] or ""})
            else:
                events.append({"type": "text", "timestamp": ts, "content": msg["content"] or ""})

        today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

        # --- Step 3: Generate draft with GPT-4o ---
        markdown = await _generate_draft(events, today)

        # --- Step 4: Derive slug + post directory path ---
        slug = _extract_slug(markdown, today)
        post_dir = f"content/drafts/{today[:4]}/{today}-{slug}"
        commit_msg = f"draft: add {today}-{slug}"

        # --- Step 5: Commit to GitHub ---
        commit_url = await github_client.commit_post(
            post_dir=post_dir,
            markdown=markdown,
            images=images,
            commit_message=commit_msg,
            md_filename="index.md",
        )

        # Notify user
        await bot.send_message(
            chat_id=user_id,
            text=f"Draft saved.\n\n`{post_dir}/post.md`\n\n{commit_url}",
            parse_mode="Markdown",
        )

    except Exception:
        logger.exception("Error processing session for user %s", user_id)
        await bot.send_message(
            chat_id=user_id,
            text="Something went wrong processing your draft. Check the logs.",
        )
    finally:
        await storage.delete_session(user_id)
        # Clean up local session files
        _cleanup(session_dir)


async def _download_file(bot: Bot, file_id: str) -> bytes | None:
    try:
        tg_file = await bot.get_file(file_id)
        if tg_file.file_size and tg_file.file_size > MAX_FILE_BYTES:
            logger.warning("File %s too large (%s bytes) — skipping", file_id, tg_file.file_size)
            return None
        async with httpx.AsyncClient() as client:
            resp = await client.get(tg_file.file_path)
            resp.raise_for_status()
            return resp.content
    except Exception:
        logger.exception("Failed to download file %s", file_id)
        return None


async def _transcribe(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            result = await _openai().audio.transcriptions.create(
                model="whisper-1",
                file=f,
            )
        return result.text
    except Exception:
        logger.exception("Whisper transcription failed for %s", path)
        return "[transcription failed]"


async def _generate_draft(events: list[dict], date: str) -> str:
    user_prompt = build_user_prompt(events, date)
    response = await _openai().chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(date=date)},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def _extract_slug(markdown: str, date: str) -> str:
    """Pull slug from frontmatter, or fall back to date-based slug."""
    match = re.search(r"^slug:\s*(.+)$", markdown, re.MULTILINE)
    if match:
        raw = match.group(1).strip().strip('"').strip("'")
        return re.sub(r"[^a-z0-9-]", "", raw.lower().replace(" ", "-"))[:60]
    return f"post-{int(time.time())}"


def _cleanup(session_dir: Path) -> None:
    try:
        if session_dir.exists():
            import shutil
            shutil.rmtree(session_dir)
    except Exception:
        logger.warning("Could not clean up session dir %s", session_dir)
