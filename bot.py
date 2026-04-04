#!/usr/bin/env python3
"""
WPPEX USERBOT - Telegram Automated Daily Message Scheduler
Sends scheduled messages to 3 Telegram groups at set times (Nigeria WAT = UTC+1)
"""

import os
import asyncio
import logging
import pytz
from datetime import datetime
from telethon import TelegramClient
from telethon.sessions import StringSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# ── Credentials from environment ──────────────────────────────────────────────
API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE    = os.environ["TELEGRAM_PHONE"]
SESSION  = os.environ.get("TELEGRAM_SESSION", "")  # StringSession string (filled after first login)

# ── Target groups ─────────────────────────────────────────────────────────────
# These IDs were provided by the user (supergroup IDs need -100 prefix)
RAW_IDS = [
    1005275946718,
    1005211906510,
    1005292682098,
]
GROUP_IDS = [int(f"-100{gid}") for gid in RAW_IDS]

# ── Timezone ──────────────────────────────────────────────────────────────────
WAT = pytz.timezone("Africa/Lagos")  # UTC+1 (Nigeria / West Africa Time)

# ── Messages ──────────────────────────────────────────────────────────────────
# Telegram bold = **text** in markdown, but Telethon uses parse_mode="markdown"
# Premium animated emoji use the custom emoji syntax: <emoji id="...">...</emoji>
# We use HTML parse mode so we can mix bold + custom emoji properly.

MSG_6_50 = (
    "<b>🚨🚨🚨🚨 The first trading signal will be released in 10 minutes, "
    "be prepared not to miss an order because there is no compensation for missed signals, "
    "always be ready to execute trades</b>"
)

MSG_7_00 = (
    "<b>The first signal invitation code has been successfully unlocked.\n"
    "Follow the instructions below to execute the trade.\n"
    "Open the 24PEX platform and complete the invitation trade order, copy the trade, and execute it.\n"
    "🚫🚫🚫Please note: All members are strictly prohibited from conducting personal trading at any time!</b>"
)

MSG_8_50 = (
    "<b>🚨🚨🚨🚨 The second signal of today will be released in 10 minutes, "
    "be prepared not to miss an order because there is no compensation for missed signals, "
    "always be ready to execute the trade</b>"
)

MSG_9_00 = (
    "<b>The second signal invitation code has been successfully unlocked.\n"
    "Follow the instructions below to execute the trade.\n"
    "Open the 24PEX platform and complete the invitation trade order, copy the trade, and execute it.\n"
    "🚫🚫🚫Please note: All members are strictly prohibited from conducting personal trading at any time!</b>"
)

MSG_12_50 = (
    "<b>Get ready to execute the bonus signal, order processing the bonus signal will be released "
    "within 10 minutes, be prepared not to miss it, there is no compensation for missed signals.</b>"
)

MSG_13_00 = (
    "<b>Bonus signal invitation code has been successfully unlocked.\n"
    "Follow the instructions below to execute the trade.\n"
    "Open the 24PEX platform and complete the invitation trade order, copy the trade, and execute it.\n"
    "🚫🚫🚫Please note: All members are strictly prohibited from conducting personal trading at any time!</b>"
)

# ── Schedule: (hour, minute, session_label, message) in WAT ──────────────────
SCHEDULE = [
    (6,  50, "First Basic Signal",  MSG_6_50),
    (7,   0, "First Basic Signal",  MSG_7_00),
    (8,  50, "Second Basic Signal", MSG_8_50),
    (9,   0, "Second Basic Signal", MSG_9_00),
    (12, 50, "Bonus Signal",        MSG_12_50),
    (13,  0, "Bonus Signal",        MSG_13_00),
]


def seconds_until(hour: int, minute: int, tz: pytz.BaseTzInfo) -> float:
    """Return seconds until the next occurrence of hour:minute in the given TZ."""
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        # Already passed today — schedule for tomorrow
        from datetime import timedelta
        target += timedelta(days=1)
    delta = (target - now).total_seconds()
    return delta


async def send_to_all_groups(client: TelegramClient, message: str, label: str):
    """Send the given message to all configured groups."""
    for gid in GROUP_IDS:
        try:
            await client.send_message(gid, message, parse_mode="html")
            logger.info(f"[{label}] Sent to group {gid}")
        except Exception as e:
            logger.error(f"[{label}] Failed to send to group {gid}: {e}")


async def schedule_job(client: TelegramClient, hour: int, minute: int, label: str, message: str):
    """Wait until next occurrence of hour:minute WAT, send message, then repeat daily."""
    while True:
        wait_secs = seconds_until(hour, minute, WAT)
        next_time = datetime.now(WAT).strftime("%Y-%m-%d") + f" {hour:02d}:{minute:02d} WAT"
        logger.info(f"[{label}] Next send at {next_time} — waiting {wait_secs/3600:.2f}h ({wait_secs:.0f}s)")
        await asyncio.sleep(wait_secs)
        logger.info(f"[{label}] Sending message now ({hour:02d}:{minute:02d} WAT)")
        await send_to_all_groups(client, message, label)
        # Sleep 61 seconds to clear the minute window before recalculating
        await asyncio.sleep(61)


async def main():
    session = StringSession(SESSION) if SESSION else StringSession()
    client = TelegramClient(session, API_ID, API_HASH)

    logger.info("Connecting to Telegram...")
    await client.start(phone=PHONE)
    logger.info("Connected successfully.")

    # On first run (no SESSION), print the session string so it can be saved
    if not SESSION:
        session_str = client.session.save()
        logger.info("=" * 60)
        logger.info("FIRST-RUN: Save this session string as the secret TELEGRAM_SESSION")
        logger.info(f"SESSION STRING: {session_str}")
        logger.info("=" * 60)

    logger.info(f"Scheduling {len(SCHEDULE)} daily messages to {len(GROUP_IDS)} groups")
    logger.info(f"Groups: {GROUP_IDS}")

    tasks = [
        asyncio.create_task(
            schedule_job(client, hour, minute, label, message)
        )
        for (hour, minute, label, message) in SCHEDULE
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
