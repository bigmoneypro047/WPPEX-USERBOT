import asyncio
import os
import logging
import threading
from datetime import datetime
from flask import Flask, request, render_template_string, session
import pytz
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, SessionPasswordNeededError
import schedule

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
GROUPS = [GROUP_1, GROUP_2, GROUP_3]

app = Flask(__name__)
app.secret_key = FLASK_SECRET

_tg_client = None
_phone_code_hash = None


def run_async(coro):
    """Run an async coroutine safely from any thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


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
                 word-break: break-all; color: #79c0ff; margin: 12px 0; max-height: 150px; overflow-y: auto; }
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
  <h1>WPPEX USERBOT Setup</h1>
  <p>Enter the phone number linked to your Telegram account to get started. You will receive an SMS verification code.</p>
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
  <p>Copy the string below, then go to your <strong>Render dashboard → Environment Variables</strong>, add a new variable named <strong>TELEGRAM_SESSION_STRING</strong> and paste it as the value. Then click Save — Render will redeploy and the bot will start running!</p>
  <div class="session-box" id="sess">{{ session_string }}</div>
  <button class="copy-btn" onclick="copySession()">📋 Copy Session String</button>
  <script>
    function copySession() {
      var text = document.getElementById('sess').innerText;
      navigator.clipboard.writeText(text).then(function() {
        event.target.innerText = '✅ Copied!';
        setTimeout(function() { event.target.innerText = '📋 Copy Session String'; }, 3000);
      });
    }
  </script>
</div>
"""

RUNNING_PAGE = STYLE + """
<div class="card">
  <div class="logo">🚀</div>
  <h1>WPPEX USERBOT</h1>
  <div class="success"><span class="status-dot"></span>Bot is active and sending messages on schedule</div>
  <p style="margin-top:16px"><strong>Daily Schedule (Nigeria Time / WAT)</strong></p>
  <p style="margin-top:14px; line-height:2">
    3:50 AM — Extra Signal warning<br>
    4:00 AM — Extra Signal instructions<br>
    11:50 AM — First Signal warning<br>
    12:00 PM — First Signal instructions<br>
    1:50 PM — Second Signal warning<br>
    2:00 PM — Second Signal instructions
  </p>
</div>
"""


@app.route("/")
def index():
    if SESSION_STRING:
        return render_template_string(RUNNING_PAGE)
    return render_template_string(PHONE_PAGE, error=None)


@app.route("/send-code", methods=["POST"])
def send_code():
    global _tg_client, _phone_code_hash
    phone = request.form.get("phone", "").strip()
    if not phone:
        return render_template_string(PHONE_PAGE, error="Please enter a phone number.")

    async def do_send():
        global _tg_client, _phone_code_hash
        _tg_client = TelegramClient(StringSession(), API_ID, API_HASH)
        await _tg_client.connect()
        result = await _tg_client.send_code_request(phone)
        _phone_code_hash = result.phone_code_hash

    try:
        run_async(do_send())
        session["phone"] = phone
        return render_template_string(CODE_PAGE, phone=phone, error=None)
    except Exception as e:
        logger.error(f"send_code error: {e}")
        return render_template_string(PHONE_PAGE, error=f"Error: {str(e)}")


@app.route("/verify-code", methods=["POST"])
def verify_code():
    global _tg_client, _phone_code_hash
    code = request.form.get("code", "").strip()
    phone = request.form.get("phone", session.get("phone", "")).strip()

    async def do_verify():
        await _tg_client.sign_in(phone=phone, code=code, phone_code_hash=_phone_code_hash)
        return _tg_client.session.save()

    try:
        sess = run_async(do_verify())
        return render_template_string(SESSION_PAGE, session_string=sess)
    except SessionPasswordNeededError:
        return render_template_string(PASSWORD_PAGE, error=None)
    except Exception as e:
        logger.error(f"verify_code error: {e}")
        return render_template_string(CODE_PAGE, phone=phone, error=f"Invalid code: {str(e)}")


@app.route("/verify-password", methods=["POST"])
def verify_password():
    global _tg_client
    password = request.form.get("password", "").strip()

    async def do_2fa():
        await _tg_client.sign_in(password=password)
        return _tg_client.session.save()

    try:
        sess = run_async(do_2fa())
        return render_template_string(SESSION_PAGE, session_string=sess)
    except Exception as e:
        logger.error(f"verify_password error: {e}")
        return render_template_string(PASSWORD_PAGE, error=f"Wrong password: {str(e)}")


bot_client = None
bot_loop = None


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
    asyncio.run_coroutine_threadsafe(send_to_all_groups(message, label), bot_loop)


def get_utc(nigeria_h, nigeria_m):
    now = datetime.now(NIGERIA_TZ)
    target = now.replace(hour=nigeria_h, minute=nigeria_m, second=0, microsecond=0)
    return target.astimezone(pytz.utc).strftime("%H:%M")


def run_scheduler_thread():
    schedule.every().day.at(get_utc(3, 50)).do(fire_job, MSG_350AM, "Extra Signal")
    schedule.every().day.at(get_utc(4, 0)).do(fire_job, MSG_400AM, "Extra Signal")
    schedule.every().day.at(get_utc(11, 50)).do(fire_job, MSG_1150AM, "First Basic Signal")
    schedule.every().day.at(get_utc(12, 0)).do(fire_job, MSG_1200PM, "First Basic Signal")
    schedule.every().day.at(get_utc(13, 50)).do(fire_job, MSG_150PM, "Second Basic Signal")
    schedule.every().day.at(get_utc(14, 0)).do(fire_job, MSG_200PM, "Second Basic Signal")
    logger.info("Scheduler started. Next jobs:")
    for job in schedule.jobs:
        logger.info(f"  {job}")
    import time
    while True:
        schedule.run_pending()
        time.sleep(30)


async def bot_main():
    global bot_client, bot_loop
    bot_loop = asyncio.get_event_loop()
    bot_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await bot_client.connect()
    if not await bot_client.is_user_authorized():
        logger.error("Session not authorized! Please go to the web URL and re-authenticate.")
        return
    me = await bot_client.get_me()
    logger.info(f"Logged in as: {me.first_name} (@{me.username})")
    t = threading.Thread(target=run_scheduler_thread, daemon=True)
    t.start()
    await bot_client.run_until_disconnected()


if __name__ == "__main__":
    if SESSION_STRING:
        t = threading.Thread(target=lambda: asyncio.run(bot_main()), daemon=True)
        t.start()
        logger.info("Bot scheduler thread started.")

    logger.info(f"Starting web server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)
