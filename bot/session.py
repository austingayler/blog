"""
Sliding-window session manager.

Each user gets one asyncio.TimerHandle. Every new message cancels the
existing handle and schedules a fresh one GROUPING_TIMEOUT_SECONDS in
the future. When the timer fires, it calls the provided callback with
the user_id so the processor can run.
"""

import asyncio
import logging
import os
import time
from typing import Awaitable, Callable

import storage

logger = logging.getLogger(__name__)

TIMEOUT = int(os.getenv("GROUPING_TIMEOUT_SECONDS", "3600"))

# user_id -> asyncio.TimerHandle
_timers: dict[int, asyncio.TimerHandle] = {}

# injected by main.py after the event loop exists
_callback: Callable[[int], Awaitable[None]] | None = None


def set_callback(cb: Callable[[int], Awaitable[None]]) -> None:
    global _callback
    _callback = cb


async def touch(user_id: int) -> None:
    """
    Called on every incoming message for a user.
    Resets the sliding window timer and persists last_activity.
    """
    await storage.touch_session(user_id)

    loop = asyncio.get_event_loop()

    # Cancel existing timer if any
    if user_id in _timers:
        _timers[user_id].cancel()

    handle = loop.call_later(TIMEOUT, _fire, user_id)
    _timers[user_id] = handle
    logger.debug("Timer reset for user %s (%ss)", user_id, TIMEOUT)


def _fire(user_id: int) -> None:
    """Sync wrapper called by call_later; schedules the async callback."""
    _timers.pop(user_id, None)
    if _callback is None:
        logger.error("Session timer fired but no callback registered")
        return
    asyncio.ensure_future(_callback(user_id))


async def restore_timers() -> None:
    """
    Called at startup. Re-schedules timers for any sessions that were
    active when the process last died, based on their last_activity +
    TIMEOUT. If the window has already expired, fires immediately.
    """
    sessions = await storage.get_active_sessions()
    now = time.time()
    loop = asyncio.get_event_loop()

    for sess in sessions:
        user_id = sess["user_id"]
        remaining = (sess["last_activity"] + TIMEOUT) - now
        delay = max(0.0, remaining)
        logger.info(
            "Restoring timer for user %s (fires in %.0fs)", user_id, delay
        )
        handle = loop.call_later(delay, _fire, user_id)
        _timers[user_id] = handle


def cancel(user_id: int) -> None:
    """Cancel a user's timer (e.g. after successful processing)."""
    handle = _timers.pop(user_id, None)
    if handle:
        handle.cancel()
