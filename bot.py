import asyncio
import os
import logging
import threading
from concurrent.futures import Future
from datetime import datetime
import urllib.request
from flask import Flask, request, render_template_string, session
import pytz
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.functions.messages import EditChatDefaultBannedRightsRequest
from telethon.tl.types import ChatBannedRights
import schedule
import time as time_mod

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
GROUP_1 = os.environ["TELEGRAM_GROUP_1"]
GROUP_2 = os.environ["TELEGRAM_GROUP_2"]
GROUP_3 = os.environ["TELEGRAM_GROUP_3"]
SESSION_STRING = os.environ.get("TELEGRAM_SESSION_STRING", "")
FLASK_SECRET = os.environ.get("SESSION_SECRET", "wppex-secret-2024")
PORT = int(os.environ.get("PORT", 10000))

NIGERIA_TZ = pytz.timezone("Africa/Lagos")
RAW_GROUPS = [GROUP_1.strip(), GROUP_2.strip(), GROUP_3.strip()]
GROUPS = []          # filled with resolved InputPeerChannel objects at startup

app = Flask(__name__)
app.secret_key = FLASK_SECRET

# Single persistent event loop running in background thread
_loop = asyncio.new_event_loop()
_setup_client = None
_phone_code_hash = None


def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()


_loop_thread = threading.Thread(target=start_background_loop, args=(_loop,), daemon=True)
_loop_thread.start()


def run_in_loop(coro, timeout=30):
    """Submit a coroutine to the persistent loop and wait for the result."""
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=timeout)


MSG_350AM = (
    "**\U0001faa7 Next, 5 Bonus signals will be released, members, please open your Wppex accounts and prepare to receive the transaction order! "
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
    "**\U0001faa7 Next, first signal of the day is about to be released, members, please open your Wppex accounts and prepare to receive the transaction order! "
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
    "**\U0001faa7 Next, second signal of the day is about to be released, members, please open your Wppex accounts and prepare to receive the transaction order! "
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

MORNING_GREETINGS = [
    (
        "**\U0001f305 Good morning, WPPEX family! \U0001f4aa\n\n"
        "A brand new day, a brand new opportunity to grow your wealth! \U0001f4b0\n"
        "Stay focused, stay disciplined, and get ready — signals are loading! \U0001f7e2\n\n"
        "Wishing everyone a profitable and blessed Monday! \U0001f64f\U0001f525**"
    ),
    (
        "**\U0001f31e Rise and shine, WPPEX warriors! \U0001f6e1\ufe0f\n\n"
        "Tuesday is here and so is another chance to secure your financial future! \U0001f4c8\n"
        "Keep your accounts ready, your mind sharp, and your eyes on the signals! \U0001f440\n\n"
        "Let's make today count — big moves ahead! \U0001f680\U0001f4b8**"
    ),
    (
        "**\U0001f4ab Good morning, champions! \U0001f3c6\n\n"
        "Wednesday energy is unmatched — we are halfway through the week and the profits keep coming! \U0001f4b5\n"
        "Open your Wppex accounts, stay alert, and follow every signal with precision! \U0001f3af\n\n"
        "Today is a great day to win! \U0001f91d\U0001f525**"
    ),
    (
        "**\U0001f303 Good morning, WPPEX community! \U0001f30d\n\n"
        "Thursday brings new strength and new signals! \U0001f4aa\n"
        "The market waits for no one — be ready, be fast, and copy every trade on time! \u23f1\ufe0f\U0001f4b9\n\n"
        "Your financial breakthrough is closer than you think! \U0001f64c\U0001f31f**"
    ),
    (
        "**\U0001f305 Wakey wakey, WPPEX family! \U0001f60a\n\n"
        "It is Friday and we are ending the week STRONG! \U0001f4aa\U0001f525\n"
        "Get your accounts loaded and ready — the signals today are going to be powerful! \u26a1\ufe0f\U0001f4b0\n\n"
        "Stay blessed, stay ready, and let us finish this week in profit! \U0001f64f\U0001f4c8**"
    ),
    (
        "**\U0001f31f Good morning, WPPEX traders! \U0001f30a\n\n"
        "Saturday means the hustle never stops for those who want real financial freedom! \U0001f5dd\ufe0f\n"
        "Our professional traders are working hard so you can win — open your app and be prepared! \U0001f4f2\U0001f4b8\n\n"
        "Grateful for this community — let us grow together today! \U0001f91d\U0001f305**"
    ),
    (
        "**\U0001f64f Good morning and happy Sunday, WPPEX family! \u2728\n\n"
        "Even on Sunday, we work because financial freedom does not take days off! \U0001f4aa\U0001f4b0\n"
        "Rest your body but keep your Wppex account active and ready for today's signals! \U0001f7e2\U0001f4f2\n\n"
        "May this week bring everyone massive profits and blessings! \U0001f31f\U0001f64c**"
    ),
]


def get_morning_greeting() -> str:
    day_index = datetime.now(NIGERIA_TZ).weekday()
    return MORNING_GREETINGS[day_index]


STYLE = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0d1117; color: #e6edf3; min-height: 100vh;
         display: flex; align-items: center; justify-content: center; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px;
          padding: 40px; max-width: 480px; width: 90%; }
  h1 { font-size: 22px; margin-bottom: 8px; color: #58a6ff; }
  p { color: #8b949e; font-size: 14px; margin-bottom: 24px; line-height: 1.5; }
  input { width: 100%; padding: 12px 14px; background: #0d1117;
          border: 1px solid #30363d; border-radius: 8px; color: #e6edf3;
          font-size: 16px; margin-bottom: 16px; outline: none; }
  input:focus { border-color: #58a6ff; }
  button { width: 100%; padding: 13px; background: #238636; border: none;
           border-radius: 8px; color: #fff; font-size: 16px; font-weight: 600;
           cursor: pointer; }
  button:hover { background: #2ea043; }
  .error { background: #3d1a1a; border: 1px solid #f85149; border-radius: 8px;
           padding: 12px 14px; color: #f85149; font-size: 14px; margin-bottom: 16px; }
  .success { background: #1a3d2a; border: 1px solid #3fb950; border-radius: 8px;
             padding: 12px 14px; color: #3fb950; font-size: 14px; margin-bottom: 16px; }
  .session-box { background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
                 padding: 14px; font-family: monospace; font-size: 11px;
                 word-break: break-all; color: #79c0ff; margin: 12px 0;
                 max-height: 150px; overflow-y: auto; }
  .copy-btn { background: #1f6feb; margin-top: 8px; }
  .copy-btn:hover { background: #388bfd; }
  .status-dot { display: inline-block; width: 10px; height: 10px;
                background: #3fb950; border-radius: 50%; margin-right: 8px; }
  .logo { font-size: 32px; margin-bottom: 12px; }
</style>
"""

PHONE_PAGE = STYLE + """
<div class="card">
  <div class="logo">🤖</div>
  <h1>PROFESSOR Setup</h1>
  <p>Enter the phone number linked to your Telegram account. You will receive an SMS verification code.</p>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST" action="/send-code">
    <input type="tel" name="phone" placeholder="+2348012345678" required autofocus>
    <button type="submit">Send Verification Code →</button>
  </form>
</div>
"""

CODE_PAGE = STYLE + """
<div class="card">
  <div class="logo">📱</div>
  <h1>Enter Verification Code</h1>
  <p>A code was sent to <strong>{{ phone }}</strong> via Telegram. Enter it below.</p>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST" action="/verify-code">
    <input type="text" name="code" placeholder="12345" maxlength="10" required autofocus>
    <input type="hidden" name="phone" value="{{ phone }}">
    <button type="submit">Verify & Generate Session →</button>
  </form>
</div>
"""

PASSWORD_PAGE = STYLE + """
<div class="card">
  <div class="logo">🔐</div>
  <h1>Two-Step Verification</h1>
  <p>Your account has 2FA enabled. Enter your Telegram cloud password.</p>
  {% if error %}<div class="error">{{ error }}</div>{% endif %}
  <form method="POST" action="/verify-password">
    <input type="password" name="password" placeholder="Your Telegram password" required autofocus>
    <button type="submit">Confirm Password →</button>
  </form>
</div>
"""

SESSION_PAGE = STYLE + """
<div class="card">
  <div class="logo">✅</div>
  <h1>Login Successful!</h1>
  <div class="success">Your session string has been generated.</div>
  <p>Copy the string below. Then go to your <strong>Render dashboard → Environment Variables</strong>, add a new variable named <strong>TELEGRAM_SESSION_STRING</strong> and paste it as the value. Save and redeploy — the bot will start running!</p>
  <div class="session-box" id="sess">{{ session_string }}</div>
  <button class="copy-btn" onclick="copySession(this)">📋 Copy Session String</button>
  <script>
    function copySession(btn) {
      navigator.clipboard.writeText(document.getElementById('sess').innerText);
      btn.innerText = '✅ Copied!';
      setTimeout(function(){ btn.innerText = '📋 Copy Session String'; }, 3000);
    }
  </script>
</div>
"""

RUNNING_PAGE = STYLE + """
<div class="card">
  <div class="logo">🚀</div>
  <h1>PROFESSOR</h1>
  <div class="success"><span class="status-dot"></span>Bot is active and sending messages on schedule</div>
  <p style="margin-top:16px"><strong>Daily Schedule (Nigeria Time / WAT)</strong></p>
  <p style="margin-top:14px; line-height:2.2">
    🔓 3:00 AM — Groups unlocked + daily greeting sent<br>
    🔒 3:30 AM — Groups locked<br>
    3:50 AM — Extra Signal warning<br>
    4:00 AM — Extra Signal instructions<br>
    🔓 4:05 AM — Groups unlocked<br><br>
    🔒 11:30 AM — Groups locked<br>
    11:50 AM — First Signal warning<br>
    12:00 PM — First Signal instructions<br>
    🔓 12:05 PM — Groups unlocked<br><br>
    🔒 1:30 PM — Groups locked<br>
    1:50 PM — Second Signal warning<br>
    2:00 PM — Second Signal instructions<br>
    🔓 2:05 PM — Groups unlocked<br><br>
    🔒 5:00 PM — Groups locked for the night
  </p>
</div>
"""


@app.route("/ping")
def ping():
    return "pong", 200


@app.route("/")
def index():
    if SESSION_STRING:
        return render_template_string(RUNNING_PAGE)
    return render_template_string(PHONE_PAGE, error=None)


@app.route("/send-code", methods=["POST"])
def send_code():
    global _setup_client, _phone_code_hash
    phone = request.form.get("phone", "").strip()
    if not phone:
        return render_template_string(PHONE_PAGE, error="Please enter a phone number.")

    async def do_send():
        global _setup_client, _phone_code_hash
        _setup_client = TelegramClient(StringSession(), API_ID, API_HASH)
        await _setup_client.connect()
        result = await _setup_client.send_code_request(phone)
        _phone_code_hash = result.phone_code_hash

    try:
        run_in_loop(do_send())
        session["phone"] = phone
        return render_template_string(CODE_PAGE, phone=phone, error=None)
    except Exception as e:
        logger.error(f"send_code error: {e}")
        return render_template_string(PHONE_PAGE, error=f"Error: {str(e)}")


@app.route("/verify-code", methods=["POST"])
def verify_code():
    global _setup_client, _phone_code_hash
    code = request.form.get("code", "").strip()
    phone = request.form.get("phone", session.get("phone", "")).strip()

    async def do_verify():
        await _setup_client.sign_in(phone=phone, code=code, phone_code_hash=_phone_code_hash)
        return _setup_client.session.save()

    try:
        sess = run_in_loop(do_verify())
        return render_template_string(SESSION_PAGE, session_string=sess)
    except SessionPasswordNeededError:
        return render_template_string(PASSWORD_PAGE, error=None)
    except Exception as e:
        logger.error(f"verify_code error: {e}")
        return render_template_string(CODE_PAGE, phone=phone, error=f"Wrong code: {str(e)}")


@app.route("/verify-password", methods=["POST"])
def verify_password():
    global _setup_client
    password = request.form.get("password", "").strip()

    async def do_2fa():
        await _setup_client.sign_in(password=password)
        return _setup_client.session.save()

    try:
        sess = run_in_loop(do_2fa())
        return render_template_string(SESSION_PAGE, session_string=sess)
    except Exception as e:
        logger.error(f"verify_password error: {e}")
        return render_template_string(PASSWORD_PAGE, error=f"Wrong password: {str(e)}")


# ── Bot scheduler (only runs when SESSION_STRING is set) ─────────────────────

bot_client = None


async def lock_all_groups(label: str):
    logger.info(f"[{label}] Locking {len(GROUPS)} group(s)...")
    for group in GROUPS:
        title = getattr(group, 'title', str(group.id))
        try:
            await bot_client(EditChatDefaultBannedRightsRequest(
                peer=group,
                banned_rights=ChatBannedRights(
                    until_date=None,
                    send_messages=True,
                    send_media=True,
                    send_stickers=True,
                    send_gifs=True,
                    send_games=True,
                    send_inline=True,
                    embed_links=True,
                )
            ))
            logger.info(f"[{label}] 🔒 Locked '{title}'")
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"[{label}] ✗ Failed to lock '{title}': {type(e).__name__}: {e}")


async def unlock_all_groups(label: str):
    logger.info(f"[{label}] Unlocking {len(GROUPS)} group(s)...")
    for group in GROUPS:
        title = getattr(group, 'title', str(group.id))
        try:
            await bot_client(EditChatDefaultBannedRightsRequest(
                peer=group,
                banned_rights=ChatBannedRights(
                    until_date=None,
                    send_messages=False,
                    send_media=False,
                    send_stickers=False,
                    send_gifs=False,
                    send_games=False,
                    send_inline=False,
                    embed_links=False,
                )
            ))
            logger.info(f"[{label}] 🔓 Unlocked '{title}'")
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"[{label}] ✗ Failed to unlock '{title}': {type(e).__name__}: {e}")


async def send_to_all_groups(message: str, label: str):
    for group in GROUPS:
        try:
            await bot_client.send_message(group, message, parse_mode="md")
            logger.info(f"[{label}] ✓ Sent to {group}")
            await asyncio.sleep(2)
        except FloodWaitError as e:
            logger.warning(f"[{label}] FloodWait {e.seconds}s on {group}")
            await asyncio.sleep(e.seconds)
            await bot_client.send_message(group, message, parse_mode="md")
        except Exception as e:
            logger.error(f"[{label}] ✗ {group}: {e}")


def fire_job(message, label):
    asyncio.run_coroutine_threadsafe(send_to_all_groups(message, label), _loop)


def fire_lock(label):
    asyncio.run_coroutine_threadsafe(lock_all_groups(label), _loop)


def fire_unlock(label):
    asyncio.run_coroutine_threadsafe(unlock_all_groups(label), _loop)


async def morning_unlock_with_greeting():
    await unlock_all_groups("Morning Unlock")
    greeting = get_morning_greeting()
    await asyncio.sleep(2)
    for group in GROUPS:
        try:
            await bot_client.send_message(group, greeting, parse_mode="md")
            logger.info(f"[Morning Unlock] ✓ Greeting sent to {group}")
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"[Morning Unlock] ✗ {group}: {e}")


def fire_morning_unlock():
    asyncio.run_coroutine_threadsafe(morning_unlock_with_greeting(), _loop)


def get_utc(nigeria_h, nigeria_m):
    now = datetime.now(NIGERIA_TZ)
    target = now.replace(hour=nigeria_h, minute=nigeria_m, second=0, microsecond=0)
    return target.astimezone(pytz.utc).strftime("%H:%M")


def run_scheduler():
    # ── Morning unlock + greeting ────────────────────────────
    schedule.every().day.at(get_utc(3,  0)).do(fire_morning_unlock)

    # ── Session 1: Extra Signal ─────────────────────────────
    schedule.every().day.at(get_utc(3, 30)).do(fire_lock,   "Extra Signal")
    schedule.every().day.at(get_utc(3, 50)).do(fire_job,    MSG_350AM, "Extra Signal")
    schedule.every().day.at(get_utc(4,  0)).do(fire_job,    MSG_400AM, "Extra Signal")
    schedule.every().day.at(get_utc(4,  5)).do(fire_unlock, "Extra Signal")

    # ── Session 2: First Basic Signal ───────────────────────
    schedule.every().day.at(get_utc(11, 30)).do(fire_lock,   "First Basic Signal")
    schedule.every().day.at(get_utc(11, 50)).do(fire_job,    MSG_1150AM, "First Basic Signal")
    schedule.every().day.at(get_utc(12,  0)).do(fire_job,    MSG_1200PM, "First Basic Signal")
    schedule.every().day.at(get_utc(12,  5)).do(fire_unlock, "First Basic Signal")

    # ── Session 3: Second Basic Signal ──────────────────────
    schedule.every().day.at(get_utc(13, 30)).do(fire_lock,   "Second Basic Signal")
    schedule.every().day.at(get_utc(13, 50)).do(fire_job,    MSG_150PM, "Second Basic Signal")
    schedule.every().day.at(get_utc(14,  0)).do(fire_job,    MSG_200PM, "Second Basic Signal")
    schedule.every().day.at(get_utc(14,  5)).do(fire_unlock, "Second Basic Signal")

    # ── Night lock ───────────────────────────────────────────
    schedule.every().day.at(get_utc(17, 0)).do(fire_lock, "Night Lock")

    logger.info("Scheduler active. Full daily schedule (UTC):")
    for job in schedule.jobs:
        logger.info(f"  {job}")
    while True:
        schedule.run_pending()
        time_mod.sleep(30)


def raw_id(val: str) -> int:
    """Return the bare positive channel ID.
    Handles both Bot-API format (-1001003257839303) and plain IDs (1003257839303).
    """
    n = int(val.strip())
    if n < 0:
        # Bot API format: -1001003257839303 → strip leading -100 → 1003257839303
        s = str(-n)
        if s.startswith("100") and len(s) > 12:
            return int(s[3:])
        return -n
    return n


async def resolve_groups():
    """Scan account dialogs to find the 3 target groups by their ID."""
    global GROUPS
    target_ids = {raw_id(r) for r in RAW_GROUPS}
    logger.info(f"[Startup] Looking for group IDs: {target_ids}")
    found = {}
    async for dialog in bot_client.iter_dialogs():
        eid = dialog.entity.id
        if eid in target_ids:
            found[eid] = dialog.entity
            logger.info(f"[Startup] ✓ Found: '{dialog.title}' (id={eid})")
        if len(found) == len(target_ids):
            break
    GROUPS.clear()
    # Keep same order as RAW_GROUPS
    for r in RAW_GROUPS:
        rid = raw_id(r)
        if rid in found:
            GROUPS.append(found[rid])
        else:
            logger.error(f"[Startup] ✗ Group ID {rid} NOT found in account dialogs — "
                         f"make sure the logged-in account is a member of that group!")
    logger.info(f"[Startup] {len(GROUPS)}/3 groups ready for lock/unlock/send.")


async def start_bot():
    global bot_client
    bot_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await bot_client.connect()
    if not await bot_client.is_user_authorized():
        logger.error("Session not authorized! Visit the web URL to re-authenticate.")
        return
    me = await bot_client.get_me()
    logger.info(f"=== PROFESSOR online as: {me.first_name} (@{me.username}) ===")

    await resolve_groups()

    if not GROUPS:
        logger.error("[Startup] FATAL: 0 groups resolved. Bot will not send or lock anything.")
        return

    # Quick connectivity test — log group titles
    for g in GROUPS:
        logger.info(f"[Startup] Ready to operate in: '{g.title}'")

    sched_thread = threading.Thread(target=run_scheduler, daemon=True)
    sched_thread.start()
    await bot_client.run_until_disconnected()


def keep_alive():
    """Ping own /ping endpoint every 5 seconds so the service never sleeps."""
    self_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{PORT}").rstrip("/")
    ping_url = f"{self_url}/ping"
    logger.info(f"[KeepAlive] Starting — pinging {ping_url} every 5 seconds")
    while True:
        try:
            urllib.request.urlopen(ping_url, timeout=5)
        except Exception:
            pass
        time_mod.sleep(5)


if __name__ == "__main__":
    if SESSION_STRING:
        asyncio.run_coroutine_threadsafe(start_bot(), _loop)
        logger.info("Bot started in background loop.")

    # Start keep-alive pinger
    ka_thread = threading.Thread(target=keep_alive, daemon=True)
    ka_thread.start()

    logger.info(f"Starting web server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)
