import asyncio
import os
import logging
from datetime import datetime, time
import pytz
from telethon import TelegramClient
from telethon.errors import FloodWaitError
import schedule
import time as time_module

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE = os.environ["TELEGRAM_PHONE"]
GROUP_1 = os.environ["TELEGRAM_GROUP_1"]
GROUP_2 = os.environ["TELEGRAM_GROUP_2"]
GROUP_3 = os.environ["TELEGRAM_GROUP_3"]

NIGERIA_TZ = pytz.timezone("Africa/Lagos")

MSG_350AM = (
    "**\U0001fa27 Next, 5 Bonus signals will be released, members, please open your Wppex accounts and prepare to receive the transaction order! "
    "Once the order is received, follow all trades immediately, each trade can only be copied once. \U0001f6a8\U0001f6a8**"
)

MSG_400AM = (
    "**All 5 Bonus Signals invitation code trading feature is now open, please complete your order as soon as possible!\n\n"
    "Follow the instructions below:\n\n"
    "1\ufe0f\u20e3 UK Time: 3:00 AM\n"
    "2\ufe0f\u20e3 Open the WPPEX homepage and click on Futures.\n"
    "3\ufe0f\u20e3 Click on Follow Order .\n"
    "4\ufe0f\u20e3 Copy the professional traders .\n"
    "5\ufe0f\u20e3 Click Complete/Confirm.\n"
    "6\ufe0f\u20e3 Wait for the trading result.\n\n"
    "\U0001f6ab\U0001f6ab\U0001f6abPlease note: All members are strictly prohibited from making private trades at any time!**"
)

MSG_1150AM = (
    "**\U0001fa27 Next, first signal of the day is about to be released, members, please open your Wppex accounts and prepare to receive the transaction order! "
    "Once the order is received, copy the trade immediately . \U0001f6a8\U0001f6a8**"
)

MSG_1200PM = (
    "**The first signal invitation trading feature is now open, please complete your order as soon as possible!\n\n"
    "Follow the instructions below:\n\n"
    "1\ufe0f\u20e3 UK Time: 11:00 AM\n"
    "2\ufe0f\u20e3 Open the WPPEX homepage and click on Futures.\n"
    "3\ufe0f\u20e3 Click on Follow Order .\n"
    "4\ufe0f\u20e3 Copy the professional traders .\n"
    "5\ufe0f\u20e3 Click Complete/Confirm.\n"
    "6\ufe0f\u20e3 Wait for the trading result.\n\n"
    "\U0001f6ab\U0001f6ab\U0001f6abPlease note: All members are strictly prohibited from making private trades at any time!**"
)

MSG_150PM = (
    "**\U0001fa27 Next, second signal of the day is about to be released, members, please open your Wppex accounts and prepare to receive the transaction order! "
    "Once the order is received, copy the trade immediately . \U0001f6a8\U0001f6a8**"
)

MSG_200PM = (
    "**The second signal invitation trading feature is now open, please complete your order as soon as possible!\n\n"
    "Follow the instructions below:\n\n"
    "1\ufe0f\u20e3 UK Time: 13:00 PM\n"
    "2\ufe0f\u20e3 Open the WPPEX homepage and click on Futures.\n"
    "3\ufe0f\u20e3 Click on Follow Order .\n"
    "4\ufe0f\u20e3 Copy the professional traders .\n"
    "5\ufe0f\u20e3 Click Complete/Confirm.\n"
    "6\ufe0f\u20e3 Wait for the trading result.\n\n"
    "\U0001f6ab\U0001f6ab\U0001f6abPlease note: All members are strictly prohibited from making private trades at any time!**"
)

GROUPS = [GROUP_1, GROUP_2, GROUP_3]

client = TelegramClient("wppex_session", API_ID, API_HASH)


async def send_to_all_groups(message: str, session_name: str):
    logger.info(f"[{session_name}] Sending message to all groups...")
    for group in GROUPS:
        try:
            await client.send_message(group, message, parse_mode="md")
            logger.info(f"[{session_name}] Sent to {group}")
            await asyncio.sleep(2)
        except FloodWaitError as e:
            logger.warning(f"[{session_name}] FloodWait for {e.seconds}s on {group}")
            await asyncio.sleep(e.seconds)
            await client.send_message(group, message, parse_mode="md")
        except Exception as e:
            logger.error(f"[{session_name}] Failed to send to {group}: {e}")


def run_async(coro):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(coro)


def job_350am():
    run_async(send_to_all_groups(MSG_350AM, "Extra Signal"))


def job_400am():
    run_async(send_to_all_groups(MSG_400AM, "Extra Signal"))


def job_1150am():
    run_async(send_to_all_groups(MSG_1150AM, "First Basic Signal"))


def job_1200pm():
    run_async(send_to_all_groups(MSG_1200PM, "First Basic Signal"))


def job_150pm():
    run_async(send_to_all_groups(MSG_150PM, "Second Basic Signal"))


def job_200pm():
    run_async(send_to_all_groups(MSG_200PM, "Second Basic Signal"))


def get_nigeria_time_utc(h, m):
    """Return UTC HH:MM string for a given Nigeria time HH:MM."""
    nigeria_now = datetime.now(NIGERIA_TZ)
    nigeria_target = nigeria_now.replace(hour=h, minute=m, second=0, microsecond=0)
    utc_target = nigeria_target.astimezone(pytz.utc)
    return utc_target.strftime("%H:%M")


def setup_schedule():
    schedule.every().day.at(get_nigeria_time_utc(3, 50)).do(job_350am)
    schedule.every().day.at(get_nigeria_time_utc(4, 0)).do(job_400am)
    schedule.every().day.at(get_nigeria_time_utc(11, 50)).do(job_1150am)
    schedule.every().day.at(get_nigeria_time_utc(12, 0)).do(job_1200pm)
    schedule.every().day.at(get_nigeria_time_utc(13, 50)).do(job_150pm)
    schedule.every().day.at(get_nigeria_time_utc(14, 0)).do(job_200pm)

    logger.info("Schedule set (all times in UTC):")
    for job in schedule.jobs:
        logger.info(f"  {job}")


async def main():
    logger.info("Starting WPPEX USERBOT...")
    await client.start(phone=PHONE)
    logger.info("Telegram client started successfully.")

    setup_schedule()

    logger.info("Scheduler running. Waiting for scheduled times...")
    while True:
        schedule.run_pending()
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
