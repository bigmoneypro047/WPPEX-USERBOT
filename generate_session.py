#!/usr/bin/env python3
"""
One-time login script to generate a Telegram session string.
Run this ONCE to authenticate, then save the printed SESSION STRING
as the secret TELEGRAM_SESSION in Replit Secrets.
After that, the main scheduler.py will use it without re-prompting for a code.
"""

import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE    = os.environ["TELEGRAM_PHONE"]


async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start(phone=PHONE)
    print("\n" + "=" * 60)
    print("SUCCESS! Copy the string below and add it as Replit Secret:")
    print("  Secret name:  TELEGRAM_SESSION")
    print("  Secret value: (the long string on the next line)")
    print()
    print(client.session.save())
    print("=" * 60)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
