"""
Run this script ONCE on your local machine to generate your Telegram session string.
Then copy the printed session string and add it as TELEGRAM_SESSION_STRING on Render.

Requirements:
    pip install telethon

Usage:
    python generate_session.py
"""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(input("Enter your TELEGRAM_API_ID: ").strip())
API_HASH = input("Enter your TELEGRAM_API_HASH: ").strip()
PHONE = input("Enter your Telegram phone number (e.g. +2348012345678): ").strip()


async def generate():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start(phone=PHONE)
    session_string = client.session.save()
    await client.disconnect()

    print("\n" + "=" * 60)
    print("SUCCESS! Your session string is:")
    print("=" * 60)
    print(session_string)
    print("=" * 60)
    print("\nCopy the string above and add it to Render as:")
    print("  Environment Variable Name:  TELEGRAM_SESSION_STRING")
    print("  Value: (paste the string above)")
    print("\nKeep this string SECRET — it gives full access to your Telegram account.")


asyncio.run(generate())
