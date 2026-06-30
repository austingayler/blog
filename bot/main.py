"""
Entrypoint for the Voiceblog Telegram bot.

MODE=polling   → local development, no public URL needed
MODE=webhook   → production (Railway), self-registers webhook using
                 RAILWAY_PUBLIC_DOMAIN env var
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

import handlers
import processor
import session
import storage

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _require(var: str) -> str:
    val = os.environ.get(var)
    if not val:
        logger.error("Missing required env var: %s", var)
        sys.exit(1)
    return val


# Module-level so the session callback closure can reference app.bot
app: Application = None  # type: ignore[assignment]


async def _on_session_expired(user_id: int) -> None:
    """Callback wired into session.py; runs the processing pipeline."""
    await processor.run(user_id, app.bot)


async def _post_init(application: Application) -> None:
    """Called by PTB after the app and event loop are both ready."""
    global app
    app = application

    data_dir = os.environ.get("DATA_DIR", "./data")
    storage.configure(data_dir)
    await storage.init()

    allowed_ids = _require("TELEGRAM_ALLOWED_USER_IDS")
    handlers.configure_allowlist(allowed_ids)

    session.set_callback(_on_session_expired)
    handlers.set_process_callback(_on_session_expired)
    await session.restore_timers()

    logger.info("Bot initialised.")


def main() -> None:
    token = _require("TELEGRAM_BOT_TOKEN")

    application = (
        Application.builder()
        .token(token)
        .post_init(_post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", handlers.handle_start))
    application.add_handler(CommandHandler("done", handlers.handle_done))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text)
    )
    application.add_handler(MessageHandler(filters.VOICE, handlers.handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO, handlers.handle_photo))

    mode = os.environ.get("MODE", "polling").lower()

    if mode == "webhook":
        public_domain = _require("RAILWAY_PUBLIC_DOMAIN")
        port = int(os.environ.get("PORT", "8080"))
        webhook_url = f"https://{public_domain}/telegram"
        logger.info("Starting in webhook mode: %s", webhook_url)
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="telegram",
            webhook_url=webhook_url,
        )
    else:
        logger.info("Starting in polling mode")
        application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
