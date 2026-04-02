# WPPEX USERBOT

A Telegram userbot that sends automated daily trading signal messages to 3 Telegram groups, 6 times per day (Nigeria time).

## Schedule (Nigeria Time / WAT = UTC+1)

| Time (Nigeria) | Session Name | Message |
|---|---|---|
| 3:50 AM | Extra Signal | Bonus signals warning |
| 4:00 AM | Extra Signal | Bonus signals instructions |
| 11:50 AM | First Basic Signal | First signal warning |
| 12:00 PM | First Basic Signal | First signal instructions |
| 1:50 PM | Second Basic Signal | Second signal warning |
| 2:00 PM | Second Basic Signal | Second signal instructions |

## Deployment on Render

1. Go to [render.com](https://render.com) and create a new **Background Worker**
2. Connect this GitHub repository
3. Set the following environment variables in Render dashboard:
   - `TELEGRAM_API_ID` — your Telegram API ID from my.telegram.org
   - `TELEGRAM_API_HASH` — your Telegram API Hash from my.telegram.org
   - `TELEGRAM_PHONE` — the phone number of the Telegram account (e.g. +2348012345678)
   - `TELEGRAM_GROUP_1` — first group username or ID
   - `TELEGRAM_GROUP_2` — second group username or ID
   - `TELEGRAM_GROUP_3` — third group username or ID

### Important: First-time Login

Telethon requires a one-time login via SMS/2FA code. You must generate a session file locally first:

```bash
pip install -r requirements.txt
python bot.py
```

Follow the prompts to enter your phone verification code. A `wppex_session.session` file will be created. You can then commit this session file (it contains only your login token, not your password) or use Telethon's string session method for production deployments.

## Tech Stack

- Python 3.11+
- [Telethon](https://github.com/LonamiWebs/Telethon) — Telegram MTProto client
- [schedule](https://github.com/dbader/schedule) — Job scheduling
- [pytz](https://pythonhosted.org/pytz/) — Timezone handling
