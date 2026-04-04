# WPPEX USERBOT

Automated Telegram userbot that sends daily trading signal messages to 3 groups, 6 times per day.

## Schedule (Nigeria Time — WAT = UTC+1)

| Time      | Session Name         | Description                            |
|-----------|----------------------|----------------------------------------|
| 6:50 AM   | First Basic Signal   | "🚨 First signal in 10 minutes..."     |
| 7:00 AM   | First Basic Signal   | "First signal code unlocked..."        |
| 8:50 AM   | Second Basic Signal  | "🚨 Second signal in 10 minutes..."    |
| 9:00 AM   | Second Basic Signal  | "Second signal code unlocked..."       |
| 12:50 PM  | Bonus Signal         | "🚨 Bonus signal in 10 minutes..."     |
| 1:00 PM   | Bonus Signal         | "Bonus signal code unlocked..."        |

## Target Groups

- `-1001005275946718`
- `-1001005211906510`
- `-1001005292682098`

---

## Setup Guide

### Step 1 — Get Telegram API Credentials

1. Go to https://my.telegram.org
2. Log in → API Development Tools
3. Create an app, note down `api_id` and `api_hash`

### Step 2 — Generate Session String (one-time)

Run the login script in the Shell:

```bash
python3 userbot/login.py
```

Enter the OTP Telegram sends to your phone. Copy the long session string it prints.

### Step 3 — Required Environment Variables

| Variable          | Description                                  |
|-------------------|----------------------------------------------|
| TELEGRAM_API_ID   | Your numeric API ID from my.telegram.org     |
| TELEGRAM_API_HASH | Your API hash from my.telegram.org           |
| TELEGRAM_PHONE    | Your phone number e.g. +2348012345678        |
| TELEGRAM_SESSION  | The session string from Step 2               |

---

## Deploying to Render

1. **Push this repository to GitHub** as `WPPEX-USERBOT`

2. Go to https://render.com → **New** → **Background Worker**

3. Connect your GitHub account and select the `WPPEX-USERBOT` repository

4. Configure the service:
   - **Name**: `wppex-userbot`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python userbot/scheduler.py`

5. Under **Environment Variables**, add all 4 variables from the table above

6. Click **Create Background Worker**

Render will deploy it and it will run 24/7, sending messages at the exact scheduled times every day.

---

## Running Locally

```bash
python3 userbot/scheduler.py
```
