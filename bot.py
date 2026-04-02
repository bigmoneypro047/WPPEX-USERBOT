import asyncio
import os
import logging
import threading
import random
import json
import hashlib
from pathlib import Path
from concurrent.futures import Future
from datetime import datetime
import urllib.request
from flask import Flask, request, render_template_string, session
import pytz
from telethon import TelegramClient, events
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

TEST_GROUP_RAW = "-1003814574407"   # dedicated test group — test-send goes here only
TEST_GROUP = None   # filled at startup

# ── Member bots (4 accounts that chat in the groups to keep them active) ─────
MEMBER_SESSIONS_RAW = [
    os.environ.get("MEMBER_SESSION_1", ""),
    os.environ.get("MEMBER_SESSION_2", ""),
    os.environ.get("MEMBER_SESSION_3", ""),
    os.environ.get("MEMBER_SESSION_4", ""),
]

# Per-bot API credentials (each member account has its own Telegram app)
MEMBER_CONFIGS = [
    {
        "api_id":   int(os.environ.get("MEMBER_1_API_ID",  os.environ.get("TELEGRAM_API_ID",  "0"))),
        "api_hash":     os.environ.get("MEMBER_1_API_HASH", os.environ.get("TELEGRAM_API_HASH", "")),
    },
    {
        "api_id":   int(os.environ.get("MEMBER_2_API_ID",  os.environ.get("TELEGRAM_API_ID",  "0"))),
        "api_hash":     os.environ.get("MEMBER_2_API_HASH", os.environ.get("TELEGRAM_API_HASH", "")),
    },
    {
        "api_id":   int(os.environ.get("MEMBER_3_API_ID",  os.environ.get("TELEGRAM_API_ID",  "0"))),
        "api_hash":     os.environ.get("MEMBER_3_API_HASH", os.environ.get("TELEGRAM_API_HASH", "")),
    },
    {
        "api_id":   int(os.environ.get("MEMBER_4_API_ID",  os.environ.get("TELEGRAM_API_ID",  "0"))),
        "api_hash":     os.environ.get("MEMBER_4_API_HASH", os.environ.get("TELEGRAM_API_HASH", "")),
    },
]

MEMBER_CLIENTS = []  # list of (TelegramClient, [group_entities]) tuples
PROFESSOR_ID   = None  # set at startup so event handlers can exclude PROFESSOR

# ── Member setup flow state ───────────────────────────────────────────────────
_member_setup_client   = None
_member_phone_code_hash = None
_member_setup_slot     = 1    # which bot number (1-4) is being set up right now

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


@app.route("/test-lock")
def test_lock():
    if not SESSION_STRING:
        return "Bot not running — no session string set.", 400
    asyncio.run_coroutine_threadsafe(lock_all_groups("MANUAL TEST"), _loop)
    return "🔒 Lock triggered — check Render logs for result.", 200


@app.route("/test-unlock")
def test_unlock():
    if not SESSION_STRING:
        return "Bot not running — no session string set.", 400
    asyncio.run_coroutine_threadsafe(unlock_all_groups("MANUAL TEST"), _loop)
    return "🔓 Unlock triggered — check Render logs for result.", 200


@app.route("/debug-groups")
def debug_groups():
    """List every dialog visible to the bot account — useful for diagnosing group resolution failures."""
    if not SESSION_STRING:
        return "Bot not running — no session string set.", 400

    result_holder = {"lines": None, "error": None}

    async def _collect():
        lines = []
        for folder in (0, 1):
            label = "MAIN" if folder == 0 else "ARCHIVED"
            try:
                async for dialog in bot_client.iter_dialogs(folder=folder):
                    eid = getattr(dialog.entity, 'id', '?')
                    lines.append(f"[{label}] id={eid}  name={dialog.title}")
            except Exception as e:
                lines.append(f"[{label}] ERROR scanning folder {folder}: {e}")
        result_holder["lines"] = lines

    fut = asyncio.run_coroutine_threadsafe(_collect(), _loop)
    fut.result(timeout=30)

    lines = result_holder["lines"] or []
    target_ids = [abs(int(r.strip())) for r in RAW_GROUPS]
    header = (
        f"Bot account dialogs ({len(lines)} total)\n"
        f"Looking for IDs: {target_ids}\n"
        f"Groups resolved so far: {len(GROUPS)}/3\n"
        f"{'='*60}\n"
    )
    body = "\n".join(lines) if lines else "(no dialogs found)"
    return f"<pre>{header}{body}</pre>", 200


@app.route("/test-send")
def test_send():
    if not SESSION_STRING:
        return "Bot not running — no session string set.", 400

    msg = (
        "✅ *PROFESSOR TEST MESSAGE*\n\n"
        "Message sending is working correctly.\n\n"
        f"Main groups loaded: {len(GROUPS)}/3"
    )

    if TEST_GROUP:
        # Send only to the dedicated test group
        async def _send_test():
            try:
                await bot_client.send_message(TEST_GROUP, msg, parse_mode="md")
                logger.info(f"[TEST-SEND] ✓ Sent to test group '{TEST_GROUP.title}'")
            except Exception as e:
                logger.error(f"[TEST-SEND] ✗ {e}")
        asyncio.run_coroutine_threadsafe(_send_test(), _loop)
        return f"📨 Test message sent to test group '{TEST_GROUP.title}' — check that group in Telegram.", 200
    elif GROUPS:
        # Fallback: test group not found, use main groups
        asyncio.run_coroutine_threadsafe(send_to_all_groups(msg, "TEST-SEND"), _loop)
        return f"📨 Test message sent to {len(GROUPS)}/3 main groups (test group not available).", 200
    else:
        return "❌ No groups resolved yet — check Render logs for startup errors.", 400


@app.route("/test-promo")
def test_promo():
    """Immediately fire one promo conversation — bypasses lock guard for testing."""
    if not MEMBER_CLIENTS:
        return (
            "❌ No member bots connected. Check MEMBER_SESSION_1-4 are set in Render "
            "and that the accounts are members of the groups.", 400
        )
    # Fire a test session that ignores the lock-window guard
    asyncio.run_coroutine_threadsafe(_fire_promo_session(bypass_lock_guard=True), _loop)
    n = len(MEMBER_CLIENTS)
    grp_counts = [len(g) for _, g in MEMBER_CLIENTS]
    return (
        f"✅ Test triggered — {n} member bot(s) connected, "
        f"groups per bot: {grp_counts}. "
        "Messages will appear in ~10 min intervals per group. "
        "Each group gets its own independent conversation."
    ), 200


@app.route("/member-debug")
def member_debug():
    """Show detailed status of each member bot and their resolved groups."""
    from datetime import datetime as _dt
    now_wat = _dt.now(NIGERIA_TZ)
    lock_active = _near_lock_window(warn_minutes=25)
    lines = [
        f"<b>Time (WAT):</b> {now_wat.strftime('%H:%M:%S')}",
        f"<b>Lock guard active:</b> {'⛔ YES — promo blocked' if lock_active else '✅ NO — promo allowed'}",
        f"<b>Member bots in MEMBER_CLIENTS:</b> {len(MEMBER_CLIENTS)}",
        "<hr>",
    ]
    for i, (client, groups) in enumerate(MEMBER_CLIENTS):
        grp_names = [getattr(g, 'title', str(g.id)) for g in groups]
        lines.append(
            f"<b>Bot {i+1}:</b> {len(groups)}/3 groups → "
            + (", ".join(grp_names) if grp_names else "⚠️ NO GROUPS FOUND")
        )
    if not MEMBER_CLIENTS:
        lines.append("⚠️ No member bots connected at all.")
    return "<br>".join(lines), 200


@app.route("/member-setup")
def member_setup():
    configured = sum(1 for s in MEMBER_SESSIONS_RAW if s.strip())
    connected  = len(MEMBER_CLIENTS)
    return render_template_string("""<!DOCTYPE html>
<html><head><title>Member Bot Setup</title>
<style>body{font-family:sans-serif;max-width:520px;margin:40px auto;padding:20px}
input,select{width:100%;padding:10px;margin:8px 0;box-sizing:border-box;border:1px solid #ccc;border-radius:6px;font-size:15px}
button{width:100%;padding:12px;background:#2196F3;color:#fff;border:none;border-radius:6px;font-size:16px;cursor:pointer;margin-top:6px}
.info{background:#e8f5e9;padding:12px;border-radius:6px;margin-bottom:16px;font-size:14px}
.warn{background:#fff3e0;padding:12px;border-radius:6px;margin-bottom:16px;font-size:14px}
label{font-weight:600;font-size:14px;margin-top:8px;display:block}
</style></head><body>
<h2>🤖 Member Bot Login</h2>
<div class="info">
  Sessions configured: <b>{{ configured }}/4</b> &nbsp;|&nbsp;
  Member bots connected: <b>{{ connected }}/4</b>
</div>
<div class="warn">
  Select which bot number you are setting up, then enter that account's phone number.<br><br>
  After logging in you will get a <b>session string</b> — copy it and add it to Render as<br>
  <b>MEMBER_SESSION_1</b> / <b>MEMBER_SESSION_2</b> / etc.
</div>
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
<form method="POST" action="/member-setup/send-code">
  <label>Which bot are you setting up?</label>
  <select name="bot_slot" required>
    <option value="1">Bot 1 — +234 8156329118</option>
    <option value="2">Bot 2 — +234 707 541 3215</option>
    <option value="3">Bot 3 — +234 8112326091</option>
    <option value="4">Bot 4 — +234 704 657 5560</option>
  </select>
  <label>Phone number (with country code)</label>
  <input name="phone" type="tel" placeholder="+2348156329118" required>
  <button type="submit">Send Login Code</button>
</form>
</body></html>""", configured=configured, connected=connected, error=None)


@app.route("/member-setup/send-code", methods=["POST"])
def member_send_code():
    global _member_setup_client, _member_phone_code_hash, _member_setup_slot
    phone    = request.form.get("phone", "").strip()
    bot_slot = int(request.form.get("bot_slot", "1"))
    if not phone:
        return "Phone number required.", 400

    cfg = MEMBER_CONFIGS[bot_slot - 1]  # 0-indexed

    async def _send():
        global _member_setup_client, _member_phone_code_hash
        _member_setup_client = TelegramClient(
            StringSession(), cfg["api_id"], cfg["api_hash"]
        )
        await _member_setup_client.connect()
        result = await _member_setup_client.send_code_request(phone)
        _member_phone_code_hash = result.phone_code_hash

    try:
        _member_setup_slot = bot_slot
        fut = asyncio.run_coroutine_threadsafe(_send(), _loop)
        fut.result(timeout=20)
        session["member_phone"]    = phone
        session["member_bot_slot"] = bot_slot
    except Exception as e:
        return f"Error sending code: {e}", 500

    return render_template_string("""<!DOCTYPE html>
<html><head><title>Member Bot — Verify Code</title>
<style>body{font-family:sans-serif;max-width:480px;margin:40px auto;padding:20px}
input{width:100%;padding:10px;margin:8px 0;box-sizing:border-box;border:1px solid #ccc;border-radius:6px}
button{width:100%;padding:12px;background:#4caf50;color:#fff;border:none;border-radius:6px;font-size:16px;cursor:pointer}
</style></head><body>
<h2>📲 Enter the code sent to {{ phone }}</h2>
{% if error %}<p style="color:red">{{ error }}</p>{% endif %}
<form method="POST" action="/member-setup/verify-code">
  <input name="code" type="text" placeholder="12345" required>
  <button type="submit">Verify Code</button>
</form>
</body></html>""", phone=phone, error=None)


@app.route("/member-setup/verify-code", methods=["POST"])
def member_verify_code():
    global _member_setup_client, _member_phone_code_hash
    code = request.form.get("code", "").strip()
    phone = session.get("member_phone", "")

    async def _verify():
        await _member_setup_client.sign_in(phone, code, phone_code_hash=_member_phone_code_hash)
        return _member_setup_client.session.save()

    try:
        fut = asyncio.run_coroutine_threadsafe(_verify(), _loop)
        sess_str = fut.result(timeout=20)
    except SessionPasswordNeededError:
        return render_template_string("""<!DOCTYPE html>
<html><head><title>2FA Required</title>
<style>body{font-family:sans-serif;max-width:480px;margin:40px auto;padding:20px}
input{width:100%;padding:10px;margin:8px 0;box-sizing:border-box;border:1px solid #ccc;border-radius:6px}
button{width:100%;padding:12px;background:#ff9800;color:#fff;border:none;border-radius:6px;font-size:16px;cursor:pointer}
</style></head><body>
<h2>🔐 Two-Factor Authentication</h2>
<form method="POST" action="/member-setup/verify-password">
  <input name="password" type="password" placeholder="Your 2FA password">
  <button type="submit">Submit</button>
</form></body></html>""")
    except Exception as e:
        return f"Verification failed: {e}", 500

    slot = session.get("member_bot_slot", _member_setup_slot)
    return render_template_string("""<!DOCTYPE html>
<html><head><title>Member Session Ready</title>
<style>body{font-family:sans-serif;max-width:540px;margin:40px auto;padding:20px}
textarea{width:100%;height:160px;padding:10px;font-family:monospace;font-size:12px;box-sizing:border-box}
.box{background:#e8f5e9;padding:16px;border-radius:8px;margin-top:16px}
button{padding:10px 20px;background:#4caf50;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px}
</style></head><body>
<h2>✅ Bot {{ slot }} session ready!</h2>
<div class="box">
  <b>Step 1 — Copy this entire session string:</b><br><br>
  <textarea id="sess" readonly>{{ sess }}</textarea><br>
  <button onclick="navigator.clipboard.writeText(document.getElementById('sess').value)">📋 Copy to clipboard</button>
</div>
<br>
<div class="box" style="background:#e3f2fd">
  <b>Step 2 — Go to Render → wppex-userbot → Environment</b><br>
  Add a new variable:<br><br>
  Key: &nbsp;<b>MEMBER_SESSION_{{ slot }}</b><br>
  Value: &nbsp;(paste the string above)
</div>
<br>
<p>After adding all 4, click <b>Save Changes</b> and Render will redeploy automatically.</p>
<p><a href="/member-setup">← Set up next member bot</a></p>
</body></html>""", sess=sess_str, slot=slot)


@app.route("/member-setup/verify-password", methods=["POST"])
def member_verify_password():
    global _member_setup_client
    password = request.form.get("password", "")

    async def _2fa():
        await _member_setup_client.sign_in(password=password)
        return _member_setup_client.session.save()

    try:
        fut = asyncio.run_coroutine_threadsafe(_2fa(), _loop)
        sess_str = fut.result(timeout=20)
    except Exception as e:
        return f"2FA failed: {e}", 500

    slot = session.get("member_bot_slot", _member_setup_slot)
    return render_template_string("""<!DOCTYPE html>
<html><head><title>Member Session Ready</title>
<style>body{font-family:sans-serif;max-width:540px;margin:40px auto;padding:20px}
textarea{width:100%;height:160px;padding:10px;font-family:monospace;font-size:12px;box-sizing:border-box}
.box{background:#e8f5e9;padding:16px;border-radius:8px;margin-top:16px}
button{padding:10px 20px;background:#4caf50;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:14px}
</style></head><body>
<h2>✅ Bot {{ slot }} session ready!</h2>
<div class="box">
  <b>Step 1 — Copy this entire session string:</b><br><br>
  <textarea id="sess" readonly>{{ sess }}</textarea><br>
  <button onclick="navigator.clipboard.writeText(document.getElementById('sess').value)">📋 Copy to clipboard</button>
</div>
<br>
<div class="box" style="background:#e3f2fd">
  <b>Step 2 — Go to Render → wppex-userbot → Environment</b><br>
  Add a new variable:<br><br>
  Key: &nbsp;<b>MEMBER_SESSION_{{ slot }}</b><br>
  Value: &nbsp;(paste the string above)
</div>
<br>
<p>After adding all 4, click <b>Save Changes</b> and Render will redeploy automatically.</p>
<p><a href="/member-setup">← Set up next member bot</a></p>
</body></html>""", sess=sess_str, slot=slot)


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
            peer = await bot_client.get_input_entity(group)
            await bot_client(EditChatDefaultBannedRightsRequest(
                peer=peer,
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
            peer = await bot_client.get_input_entity(group)
            await bot_client(EditChatDefaultBannedRightsRequest(
                peer=peer,
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


async def catch_up_on_startup():
    """Fire any jobs missed within the last 10 minutes due to a restart."""
    now = datetime.now(NIGERIA_TZ)
    now_total = now.hour * 60 + now.minute
    WINDOW = 10  # minutes

    tasks = [
        (3,  0,  lambda: morning_unlock_with_greeting(),               "Morning Unlock"),
        (3, 30,  lambda: lock_all_groups("Extra Signal"),               "Extra Signal Lock"),
        (3, 50,  lambda: send_to_all_groups(MSG_350AM, "Extra Signal"), "Extra Signal Warning"),
        (4,  0,  lambda: send_to_all_groups(MSG_400AM, "Extra Signal"), "Extra Signal Instructions"),
        (4,  5,  lambda: unlock_all_groups("Extra Signal"),             "Extra Signal Unlock"),
        (11, 30, lambda: lock_all_groups("First Basic Signal"),          "First Signal Lock"),
        (11, 50, lambda: send_to_all_groups(MSG_1150AM, "First Basic Signal"), "First Signal Warning"),
        (12,  0, lambda: send_to_all_groups(MSG_1200PM, "First Basic Signal"), "First Signal Instructions"),
        (12,  5, lambda: unlock_all_groups("First Basic Signal"),        "First Signal Unlock"),
        (13, 30, lambda: lock_all_groups("Second Basic Signal"),         "Second Signal Lock"),
        (13, 50, lambda: send_to_all_groups(MSG_150PM, "Second Basic Signal"), "Second Signal Warning"),
        (14,  0, lambda: send_to_all_groups(MSG_200PM, "Second Basic Signal"), "Second Signal Instructions"),
        (14,  5, lambda: unlock_all_groups("Second Basic Signal"),       "Second Signal Unlock"),
        (17,  0, lambda: lock_all_groups("Night Lock"),                  "Night Lock"),
    ]

    caught = []
    for (th, tm, factory, label) in tasks:
        task_total = th * 60 + tm
        if 0 < now_total - task_total <= WINDOW:
            caught.append((label, factory))

    if not caught:
        logger.info("[CatchUp] No missed jobs detected.")
        return

    for label, factory in caught:
        logger.info(f"[CatchUp] ⚡ Replaying missed job: {label}")
        try:
            await factory()
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"[CatchUp] ✗ {label}: {e}")


# ── UK time helper & member bot message bank ─────────────────────────────────

def uk_time_str(wat_h: int, wat_m: int) -> str:
    """Convert WAT (UTC+1) to UK GMT (UTC+0) display string."""
    total = wat_h * 60 + wat_m - 60
    if total < 0:
        total += 1440
    h, m = divmod(total, 60)
    period = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {period}"


# Pre-computed signal times in UK format
_UK_EXTRA  = uk_time_str(4,  0)   # "3:00 AM"
_UK_FIRST  = uk_time_str(12, 0)   # "11:00 AM"
_UK_SECOND = uk_time_str(14, 0)   # "1:00 PM"

MORNING_MSGS = [
    "Good morning everyone 🌅",
    "GM all! Ready for today's trades 💪",
    "Morning 👋 hope everyone's accounts are ready",
    "Good morning professor and everyone 🙏",
    "Rise and shine traders! Let's make today count 🌞",
]

PRE_SIGNAL_QUESTIONS = [
    "When is the next signal today?",
    "Anyone know what time the signal is?",
    "What time is today's signal please?",
    "Is there a signal coming up soon?",
]

PRE_SIGNAL_CONFIRMS = [
    "Thanks! Getting my account ready 👀",
    "Perfect, I'll be ready 💪",
    "Got it! Preparing now 🙏",
    "Great thanks! Setting up my account ✅",
]

SIGNAL_REACTIONS = [
    "Copying now! 🚀",
    "Order placed ✅",
    "Great signal professor! 🔥",
    "Trade placed 👌 Let's go!",
    "Done! Let's get these profits 💰",
    "Copied! 🙌",
    "Let's go! 📈",
    "In the trade! 💯",
    "Signal copied ✅🚀",
    "Thanks professor! Trade is live 🔥",
]

GENERAL_MSGS = [
    "This group has been amazing for my trading 🙏",
    "Making consistent profits thanks to professor 📈",
    "Best trading group I've been in 💯",
    "Results have been great this week 📊",
    "Professor's signals are so accurate 🎯",
    "So glad I joined this group 🙌",
    "Making good returns since I joined 💰",
    "Grateful to be part of this community 🙏",
]

# ── 30-day no-repeat message tracking ────────────────────────────────────────
_SENT_HISTORY_FILE = Path("/tmp/qt_promo_sent.json")
_PROMO_COOLDOWN    = 90 * 86400  # 90 days in seconds

def _msg_key(msg: str) -> str:
    return hashlib.md5(msg.encode()).hexdigest()[:16]

def _load_sent() -> dict:
    try:
        if _SENT_HISTORY_FILE.exists():
            return json.loads(_SENT_HISTORY_FILE.read_text())
    except Exception:
        pass
    return {}

def _save_sent(history: dict):
    try:
        _SENT_HISTORY_FILE.write_text(json.dumps(history))
    except Exception:
        pass

def _available_messages(pool: list) -> list:
    """Return messages not sent in the last 30 days, sorted oldest-sent first as fallback."""
    history = _load_sent()
    now = time_mod.time()
    fresh, stale = [], []
    for msg in pool:
        sent_at = history.get(_msg_key(msg), 0)
        if now - sent_at >= _PROMO_COOLDOWN:
            fresh.append(msg)
        else:
            stale.append((sent_at, msg))
    # Fallback: if not enough fresh messages, pad with least-recently-sent
    stale.sort(key=lambda x: x[0])
    return fresh + [m for _, m in stale]

def _mark_messages_sent(msgs: list):
    history = _load_sent()
    now = time_mod.time()
    for msg in msgs:
        history[_msg_key(msg)] = now
    _save_sent(history)

# ── Topic-based conversation pool ────────────────────────────────────────────
# Each topic is a list of messages that are contextually related.
# Within a session all messages come from ONE topic so conversation stays coherent.
# A second topic may be introduced mid-session to simulate a natural topic change.
PROMO_TOPICS = {
    "copy_vs_job": [
        "Copy trading has genuinely changed my life 🙏 No more 9-5 stress",
        "I quit my 9-5 job 3 months ago and haven't looked back once 💪",
        "No boss, no commute, just follow the professor's signal and earn 😂💰",
        "Working from home beats any office job I've ever had 📊",
        "Who else here is earning while others are stuck in traffic? 😂",
        "My income has been more stable since copy trading than any salary I had 💯",
        "The 9-5 system was never built for real financial freedom 🔥",
        "Copy trading gives you time AND money — that's the real dream 🙌",
        "My lifestyle changed completely since I stopped depending on a salary 📈",
        "Imagine getting paid while you sleep — that's exactly what this is 🏠💰",
        "I used to work 12-hour days for someone else. Now I work for myself 💪",
        "Copy trading from QT is the best career change I ever made 🎯",
    ],
    "crypto_market": [
        "Crypto market is looking really strong right now 🚀",
        "Liquidity is very high today — perfect conditions for trading 📊",
        "When liquidity is strong the signals hit even better 🎯",
        "Crypto prices are moving beautifully this week 📈",
        "Professor's market timing is always on point regardless of conditions 🙌",
        "The crypto market never sleeps and neither does our income 💰",
        "Good volatility today — signals performing really well 🎯",
        "Crypto is up again — being in the right group matters so much 🚀",
        "Market is moving in our favour today 📈 Professor called it perfectly",
        "Green candles across the board — this is why we stay in this group 🔥",
        "Bitcoin is moving nicely today, perfect signal conditions 📊",
        "Market momentum is strong — professor always positions us ahead of it 💪",
    ],
    "qt_opportunity": [
        "Joining QT Investment Group is the best financial decision I've made 🙌",
        "The opportunity in this group shows up consistently every single day 📈",
        "Professor has never missed a day — always here and showing up for us 💯",
        "QT is different from every other group I've tried — real results 🔥",
        "This community genuinely wants every single member to win 🙏",
        "QT opened my eyes to what's truly possible when you're in the right place 💪",
        "The consistency here is what keeps me coming back every day 📊",
        "If you're not in QT Investment Group you're honestly missing out 🚀",
        "QT has shown me that financial freedom is not a dream — it's a plan 🎯",
        "This group changed the direction of my finances completely 🙌💰",
        "I've referred 5 people to QT and all of them are grateful now 🙏",
        "New members joining every week — the word is spreading fast 🔥",
    ],
    "referrals": [
        "Has anyone here taken advantage of the referral rewards yet? 👀",
        "I brought in 3 people last month and the referral bonuses are real 💰",
        "Referrals give you extra income on top of your daily trading profits 📊",
        "The more people you bring into QT the more everyone benefits 🙏",
        "Tell your friends — you earn from their copy trading activity too 💪",
        "Referral income is passive income stacked on top of passive income 🔥",
        "I share QT with everyone I know — the referral rewards alone are worth it 💰",
        "Bring your network in and start building residual income from referrals 📈",
        "Every person you refer adds another income stream to yours 💯",
        "My referral bonus this month covered my phone bill and data 😂💰",
        "Easy way to earn extra — just share QT with people who want to grow financially 📊",
    ],
    "team_building": [
        "Building a team inside QT is the fastest way to grow your income 💰",
        "When your team copies trades you benefit from their trading volume too 📈",
        "Team formation is how the big earners here multiply income fast 🔥",
        "Solo income is great but team income is a completely different level 🙌",
        "The more people in your team the more income streams you control 📊",
        "This is leveraged income — your team works and you all earn together 💯",
        "Our team is growing weekly and everyone's income is increasing 🙏",
        "Teamwork is the fastest path to real financial growth here 💪",
        "I started with just 2 people in my team — now we all earn consistently 🎯",
        "Every new team member adds more volume and more income for everyone 🔥",
    ],
    "stable_income": [
        "Copy trading gives stable daily income that beats any monthly salary 📊",
        "The market is open 24/7 and signals come in every single day 🌍",
        "With professor's accuracy the returns are very consistent and reliable 🙏",
        "Unlike a job, this income doesn't depend on any employer or boss 💪",
        "Stable daily income without answering to anyone — that's freedom 🏠",
        "My monthly income from copy trading now exceeds my old salary 📈",
        "Consistent. Reliable. Stable. That's what QT copy trading delivers 🎯",
        "Professor signals both rising and falling markets — income flows both ways 🔥",
        "I've not missed a single profitable month since joining QT 💰",
        "This is the most consistent income I've ever had in my life 💯",
    ],
    "forex_trading": [
        "Forex market is moving really well today — great liquidity 📈",
        "Professor covers crypto AND forex — double income opportunity every day 💪",
        "Two markets, two income streams, one group 🔥 That's real value",
        "Forex signals here are just as sharp as the crypto ones — impressive 🎯",
        "Once you understand the signals forex becomes very easy to follow 📊",
        "Forex and crypto together means income no matter which market is active 💰",
        "Professor reads both markets perfectly — that's a rare and valuable skill 🙌",
        "Forex pairs are moving nicely today alongside crypto 📈 Good session ahead",
        "The fact that we get both forex and crypto signals daily is incredible 💪",
    ],
    "simplicity": [
        "What I love most about copy trading is how genuinely simple it is 😊",
        "You don't need charts or technical knowledge — just follow professor 📱",
        "See the signal → copy the trade → wait for profit ✅ That's literally it",
        "Even total beginners can earn here — the signals do all the work 🙌",
        "I had zero trading experience when I joined, now I earn every day 💰",
        "The learning curve here is literally zero — see signal, copy, earn 📈",
        "Anyone can do this — young, old, no experience needed at all 🙏",
        "I showed my cousin how to set up last week and he's already making profit 😂",
        "This is the easiest income source I've ever found — and I've tried many 💯",
        "You don't need to understand the market — professor does that for you 🎯",
    ],
    "home_income": [
        "Earning from home without a boss is still unreal to me 🏠💰",
        "Copy trading lets you work on your own terms and schedule 📊",
        "I used to commute 2 hours every day — now that time earns me money 😂",
        "QT Investment Group gave me a completely new perspective on income 🙌",
        "My phone is my office and professor's signals are my daily work 📱💰",
        "Financial freedom isn't a dream when you're in the right community 🔥",
        "I work less and earn more since I started copy trading here 💯",
        "Location doesn't matter — I've been earning from everywhere I travel 🌍",
        "Home, holiday, anywhere — the income follows you with copy trading 💪",
    ],
}

# Flat list of every message across all topics (for 90-day tracking)
_ALL_PROMO_MSGS = [m for msgs in PROMO_TOPICS.values() for m in msgs]


def _near_lock_window(warn_minutes: int = 25) -> bool:
    """
    Returns True if the current WAT time is:
      - currently inside a signal lock window, OR
      - within `warn_minutes` minutes of one starting.
    Used to abort promo messages before they'd clash with a locked group.

    Lock windows (WAT):
      03:30 – 04:05  Extra Signal
      11:30 – 12:05  First Basic Signal
      13:30 – 14:05  Second Basic Signal
      17:00 – 03:00  Night Lock (next day)
    """
    now = datetime.now(NIGERIA_TZ)
    m   = now.hour * 60 + now.minute   # minutes since midnight WAT

    # Define each window as (lock_start_min, unlock_min)
    WINDOWS = [
        (3*60+30,  4*60+5),    # Extra Signal
        (11*60+30, 12*60+5),   # First Basic Signal
        (13*60+30, 14*60+5),   # Second Basic Signal
    ]
    # Night lock spans midnight — check separately
    night_start = 17*60   # 17:00
    night_end   = 3*60    # 03:00 next day

    for lock_start, lock_end in WINDOWS:
        # Currently inside this lock window
        if lock_start <= m < lock_end:
            return True
        # Approaching this lock window
        if lock_start - warn_minutes <= m < lock_start:
            return True

    # Night lock: locked from 17:00 to 03:00
    if m >= night_start or m < night_end:
        return True
    # Approaching night lock
    if night_start - warn_minutes <= m < night_start:
        return True

    return False


def _pick_promo_topic(exclude_topic: str = "") -> tuple:
    """Return (topic_id, shuffled_available_messages) for one independent group session."""
    candidates = []
    for tid, msgs in PROMO_TOPICS.items():
        if tid == exclude_topic:
            continue
        avail = _available_messages(msgs)
        if len(avail) >= 3:
            candidates.append((tid, avail))
    if not candidates:
        avail = _available_messages(_ALL_PROMO_MSGS)
        return ("fallback", avail)
    tid, avail = random.choice(candidates)
    random.shuffle(avail)
    return (tid, avail)


async def _fire_promo_for_group(target_group, bypass_lock_guard: bool = False):
    """
    Fire an independent topic-based conversation in a SINGLE group.
    - Picks its own topic (independent of other groups)
    - Picks its own bot order (random, non-consecutive)
    - Reply behaviour:
        * first message — always standalone (no tag)
        * after a topic-change message — standalone (fresh thread start)
        * otherwise  35% reply WITH Telegram tag
                     35% send without tag (content still on-topic)
                     30% standalone statement (no reference to previous)
    - 10-min gap between each bot turn
    - bypass_lock_guard=True skips the lock-window safety check (for /test-promo)
    """
    # ── Pick topic ────────────────────────────────────────────────────────────
    topic_id, avail_msgs = _pick_promo_topic()
    count  = random.randint(4, 6)
    chosen = avail_msgs[:count]

    # Optionally insert one topic-change message (~30% chance, 5+ msg sessions)
    topic_change_idx = None
    if len(chosen) >= 5 and random.random() < 0.30:
        other_topics = [t for t in PROMO_TOPICS if t != topic_id]
        if other_topics:
            new_tid   = random.choice(other_topics)
            new_avail = _available_messages(PROMO_TOPICS[new_tid])
            if new_avail:
                change_msg       = random.choice(new_avail)
                topic_change_idx = random.randint(3, len(chosen) - 1)
                chosen.insert(topic_change_idx, change_msg)
                logger.info(f"[Promo] '{getattr(target_group,'title',target_group.id)}' "
                            f"topic change at pos {topic_change_idx}: {new_tid}")

    # ── Find bots that have access to this specific group ────────────────────
    bots_for_group = []
    for bot_idx, (client, groups) in enumerate(MEMBER_CLIENTS):
        for g in groups:
            if _bare_id(g.id) == _bare_id(target_group.id):
                bots_for_group.append((bot_idx, client, g))
                break

    if not bots_for_group:
        logger.warning(f"[Promo] No bots have access to '{getattr(target_group,'title',target_group.id)}'")
        return

    n_bots = len(bots_for_group)

    # ── Build bot sequence ────────────────────────────────────────────────────
    bot_seq = []
    for _ in range(len(chosen)):
        opts = list(range(n_bots))
        if bot_seq and len(opts) > 1:
            opts = [b for b in opts if b != bot_seq[-1]]
        bot_seq.append(random.choice(opts))

    _mark_messages_sent(chosen)
    logger.info(f"[Promo] '{getattr(target_group,'title',target_group.id)}' | "
                f"topic={topic_id} | {len(chosen)} msgs | "
                f"bots={[bots_for_group[b][0]+1 for b in bot_seq]}")

    # ── Send messages ─────────────────────────────────────────────────────────
    last_msg_id    = None
    fresh_thread   = False   # True right after a topic change

    for i, (slot, text) in enumerate(zip(bot_seq, chosen)):
        _, client, group_entity = bots_for_group[slot]
        bot_num = bots_for_group[slot][0] + 1

        # Decide reply style
        if i == 0 or fresh_thread:
            reply_to   = None          # standalone — open new thread
            fresh_thread = False
        else:
            r = random.random()
            if r < 0.35 and last_msg_id:
                reply_to = last_msg_id  # Telegram reply tag
            elif r < 0.70:
                reply_to = None         # on-topic but no tag
            else:
                reply_to = None         # standalone statement

        # Mark if this message is a topic change (next msg starts fresh)
        if topic_change_idx is not None and i == topic_change_idx:
            fresh_thread = True

        # Safety guard — abort the whole conversation if a lock window is near
        if not bypass_lock_guard and _near_lock_window(warn_minutes=25):
            grp_title = getattr(target_group, 'title', target_group.id)
            logger.info(f"[Promo] '{grp_title}' — approaching lock window, stopping conversation.")
            return

        try:
            sent = await client.send_message(group_entity, text, reply_to=reply_to)
            last_msg_id = sent.id
            logger.info(f"[Promo] Bot{bot_num} → '{getattr(target_group,'title',target_group.id)}'"
                        + (" [tag]" if reply_to else ""))
            await asyncio.sleep(1.5)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 2)
            try:
                sent = await client.send_message(group_entity, text, reply_to=reply_to)
                last_msg_id = sent.id
            except Exception:
                pass
        except Exception as exc:
            logger.error(f"[Promo] Bot{bot_num} → '{getattr(target_group,'title',target_group.id)}': {exc}")

        # 10-minute gap between bot turns (natural group conversation pace)
        if i < len(chosen) - 1:
            await asyncio.sleep(random.uniform(560, 640))


async def _fire_promo_session(bypass_lock_guard: bool = False):
    """
    Kick off 3 independent promo conversations — one per group.
    Each group gets its own topic, its own bot order and its own start time
    so the 3 groups look completely unrelated to each other.
    bypass_lock_guard=True skips the lock-window safety check (used by /test-promo).
    """
    if not MEMBER_CLIENTS:
        logger.warning("[Promo] No member bots connected — skipping.")
        return

    # Collect all unique groups across ALL member bots (not just bot 0)
    seen_ids: set = set()
    all_groups = []
    for _, groups in MEMBER_CLIENTS:
        for g in groups:
            bid = _bare_id(g.id)
            if bid not in seen_ids:
                seen_ids.add(bid)
                all_groups.append(g)

    if not all_groups:
        logger.warning("[Promo] No groups found across any member bot.")
        return

    logger.info(f"[Promo] Firing for {len(all_groups)} group(s): "
                f"{[getattr(g,'title',g.id) for g in all_groups]}")

    # Stagger each group's conversation by 0–20 min so they don't start together
    stagger_seconds = sorted(random.uniform(0, 1200) for _ in range(len(all_groups)))

    async def delayed_promo(group, delay):
        if delay > 0:
            await asyncio.sleep(delay)
        await _fire_promo_for_group(group, bypass_lock_guard=bypass_lock_guard)

    await asyncio.gather(
        *[delayed_promo(g, s) for g, s in zip(all_groups, stagger_seconds)]
    )


def fire_promo():
    asyncio.run_coroutine_threadsafe(_fire_promo_session(), _loop)


PROF_MORNING_REPLIES = [
    "Good morning professor 🙏",
    "Welcome professor! 🌅",
    "Good morning professor, ready for today's signals 💪",
    "Morning professor! 🙏",
    "Good morning professor 🌅 Looking forward to today!",
]

READY_MSGS = [
    "Ready 👌",
    "Ready ✅",
    "Ready! 💪",
    "Prepared and waiting 👀",
    "All set ✅",
]

DONE_MSGS = [
    "Done ✅",
    "Done! 💰",
    "Done 🙌",
    "Trade complete! 📊",
    "Done, great signal as always 🎯",
]

GREETING_KEYWORDS = [
    "good morning", "morning", "good afternoon", "afternoon",
    "good evening", "evening", "hello", "hi", "hey",
    "new here", "i'm new", "im new", "just joined", "newly joined",
    "gm", "howdy", "greetings",
]

def get_greeting_response(msg: str) -> str:
    m = msg.lower()
    if any(k in m for k in ["new here", "i'm new", "im new", "just joined", "newly joined"]):
        return random.choice([
            "Welcome to the group! 🙏 You're in the right place",
            "Welcome! 🎉 Great decision joining us",
            "Welcome aboard! 🙌 You'll love it here",
            "Welcome! 😊 The best trading community online",
        ])
    elif any(k in m for k in ["good morning", "morning", "gm"]):
        return random.choice([
            "Good morning! 🌅",
            "GM! 💪",
            "Good morning! 🙏",
            "Morning! 🌞 Ready for the day",
        ])
    elif any(k in m for k in ["good afternoon", "afternoon"]):
        return random.choice([
            "Good afternoon! ☀️",
            "Good afternoon! 🙏",
            "Afternoon everyone! 😊",
        ])
    elif any(k in m for k in ["good evening", "evening"]):
        return random.choice([
            "Good evening! 🌙",
            "Good evening! 🙏",
        ])
    else:
        return random.choice([
            "Hello! 👋",
            "Hey! 👋",
            "Hi there! 🙏",
            "Greetings! 🙏",
        ])


async def setup_member_event_handlers(client, groups, bot_idx: int, member_ids: set):
    """Register a Telethon event handler so this member bot responds to greetings."""
    group_ids = [g.id for g in groups]
    me = await client.get_me()
    my_id = me.id

    @client.on(events.NewMessage(chats=group_ids, incoming=True))
    async def handle_greeting(event):
        try:
            sender = await event.get_sender()
            if sender is None:
                return
            sid = sender.id
            # Skip own messages, other member bots, and PROFESSOR
            excluded = member_ids | ({PROFESSOR_ID} if PROFESSOR_ID else set()) | {my_id}
            if sid in excluded:
                return
            msg = event.message.message or ""
            if not any(kw in msg.lower() for kw in GREETING_KEYWORDS):
                return
            # Stagger: each bot waits its own natural-feeling delay
            await asyncio.sleep(random.uniform(4, 18) + bot_idx * 9)
            response = get_greeting_response(msg)
            await client.send_message(event.chat_id, response)
            logger.info(f"[MemberBot {bot_idx+1}] Greeted back: {response!r}")
        except Exception as exc:
            logger.error(f"[MemberBot {bot_idx+1}] Greeting handler error: {exc}")


async def _resolve_member_groups(client) -> list:
    """Scan dialogs for a member bot client and return the 3 main group entities."""
    target_ids = {_bare_id(r): r.strip() for r in RAW_GROUPS}
    found = {}
    for folder in (0, 1):
        if len(found) == len(target_ids):
            break
        try:
            async for dialog in client.iter_dialogs(folder=folder):
                eid = getattr(dialog.entity, 'id', None)
                if eid is not None and eid in target_ids:
                    found[eid] = dialog.entity
                if len(found) == len(target_ids):
                    break
        except Exception:
            pass
    return [found[n] for n in target_ids if n in found]


async def start_member_bots():
    """Connect all 4 member bots that have a session string configured."""
    global MEMBER_CLIENTS
    MEMBER_CLIENTS.clear()

    # Pass 1 – connect every bot and resolve groups
    for idx, sess in enumerate(MEMBER_SESSIONS_RAW):
        if not sess.strip():
            logger.info(f"[MemberBot {idx+1}] No session — skipping.")
            continue
        try:
            cfg    = MEMBER_CONFIGS[idx]
            client = TelegramClient(StringSession(sess.strip()), cfg["api_id"], cfg["api_hash"])
            await client.connect()
            if not await client.is_user_authorized():
                logger.warning(f"[MemberBot {idx+1}] Session not authorised — skipping.")
                continue
            me = await client.get_me()
            logger.info(f"[MemberBot {idx+1}] Connected as {me.first_name} (@{me.username})")
            groups = await _resolve_member_groups(client)
            logger.info(f"[MemberBot {idx+1}] {len(groups)}/3 groups resolved.")
            MEMBER_CLIENTS.append((client, groups))
        except Exception as e:
            logger.error(f"[MemberBot {idx+1}] Failed to start: {e}")

    logger.info(f"[MemberBots] {len(MEMBER_CLIENTS)}/4 member bot(s) ready.")

    # Pass 2 – collect all member user IDs (so handlers can ignore bot-to-bot messages)
    member_ids: set = set()
    for client, _ in MEMBER_CLIENTS:
        try:
            m = await client.get_me()
            member_ids.add(m.id)
        except Exception:
            pass

    # Pass 3 – register greeting event handlers on every connected bot
    for bot_idx, (client, groups) in enumerate(MEMBER_CLIENTS):
        try:
            await setup_member_event_handlers(client, groups, bot_idx, member_ids)
            logger.info(f"[MemberBot {bot_idx+1}] Greeting event handler registered.")
        except Exception as e:
            logger.error(f"[MemberBot {bot_idx+1}] Handler setup failed: {e}")


async def _mbr_send(bot_idx: int, msg: str, label: str):
    """Send a message from member bot at bot_idx (0-based) to all 3 main groups."""
    if not MEMBER_CLIENTS:
        logger.warning(f"[{label}] No member bots connected yet.")
        return
    idx = bot_idx % len(MEMBER_CLIENTS)
    client, groups = MEMBER_CLIENTS[idx]
    for g in groups:
        try:
            await client.send_message(g, msg)
            logger.info(f"[{label}] ✓ Bot{idx+1} → '{getattr(g, 'title', g.id)}'")
            await asyncio.sleep(2)
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            await client.send_message(g, msg)
        except Exception as e:
            logger.error(f"[{label}] ✗ Bot{idx+1}: {e}")


def fire_mbr(bot_idx: int, msg: str, label: str):
    asyncio.run_coroutine_threadsafe(_mbr_send(bot_idx, msg, label), _loop)


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

    # ── Member bots reply to PROFESSOR's morning greeting (3:03–3:09 AM WAT) ──
    schedule.every().day.at(get_utc(3,  3)).do(fire_mbr, 0, random.choice(PROF_MORNING_REPLIES), "MorningReply-MBR")
    schedule.every().day.at(get_utc(3,  5)).do(fire_mbr, 1, random.choice(PROF_MORNING_REPLIES), "MorningReply-MBR")
    schedule.every().day.at(get_utc(3,  7)).do(fire_mbr, 2, random.choice(PROF_MORNING_REPLIES), "MorningReply-MBR")
    schedule.every().day.at(get_utc(3,  9)).do(fire_mbr, 3, random.choice(PROF_MORNING_REPLIES), "MorningReply-MBR")

    # ── "Ready" before extra signal lock (2 min apart each, lock at 3:30) ─────
    schedule.every().day.at(get_utc(3, 22)).do(fire_mbr, 0, random.choice(READY_MSGS), "Ready-Extra-MBR")
    schedule.every().day.at(get_utc(3, 24)).do(fire_mbr, 1, random.choice(READY_MSGS), "Ready-Extra-MBR")
    schedule.every().day.at(get_utc(3, 26)).do(fire_mbr, 2, random.choice(READY_MSGS), "Ready-Extra-MBR")
    schedule.every().day.at(get_utc(3, 28)).do(fire_mbr, 3, random.choice(READY_MSGS), "Ready-Extra-MBR")

    # ── Pre-extra-signal Q&A — once per week (Monday only) ───────────────────
    schedule.every().monday.at(get_utc(3, 46)).do(
        fire_mbr, 3, random.choice(PRE_SIGNAL_QUESTIONS), "PreExtra-MBR")
    schedule.every().monday.at(get_utc(3, 47)).do(
        fire_mbr, 0, f"Next signal is at {_UK_EXTRA} UK time 🔔", "PreExtra-MBR")
    schedule.every().monday.at(get_utc(3, 49)).do(
        fire_mbr, 1, random.choice(PRE_SIGNAL_CONFIRMS), "PreExtra-MBR")

    # ── Post-extra-signal reactions + "Done" (2 min apart each) ─────────────
    schedule.every().day.at(get_utc(4,  2)).do(fire_mbr, 2, random.choice(SIGNAL_REACTIONS), "PostExtra-MBR")
    schedule.every().day.at(get_utc(4,  4)).do(fire_mbr, 3, random.choice(SIGNAL_REACTIONS), "PostExtra-MBR")
    schedule.every().day.at(get_utc(4,  6)).do(fire_mbr, 0, random.choice(SIGNAL_REACTIONS), "PostExtra-MBR")
    schedule.every().day.at(get_utc(4,  8)).do(fire_mbr, 1, random.choice(SIGNAL_REACTIONS), "PostExtra-MBR")
    schedule.every().day.at(get_utc(4, 10)).do(fire_mbr, 0, random.choice(DONE_MSGS), "Done-Extra-MBR")
    schedule.every().day.at(get_utc(4, 12)).do(fire_mbr, 1, random.choice(DONE_MSGS), "Done-Extra-MBR")
    schedule.every().day.at(get_utc(4, 14)).do(fire_mbr, 2, random.choice(DONE_MSGS), "Done-Extra-MBR")
    schedule.every().day.at(get_utc(4, 16)).do(fire_mbr, 3, random.choice(DONE_MSGS), "Done-Extra-MBR")

    # ── General midday chat ───────────────────────────────────────────────────
    schedule.every().day.at(get_utc(8,  0)).do(fire_mbr, 1, random.choice(GENERAL_MSGS), "General-MBR")
    schedule.every().day.at(get_utc(10, 30)).do(fire_mbr, 3, random.choice(GENERAL_MSGS), "General-MBR")

    # ── "Ready" before first signal lock (2 min apart each, lock at 11:30) ────
    schedule.every().day.at(get_utc(11, 22)).do(fire_mbr, 0, random.choice(READY_MSGS), "Ready-First-MBR")
    schedule.every().day.at(get_utc(11, 24)).do(fire_mbr, 1, random.choice(READY_MSGS), "Ready-First-MBR")
    schedule.every().day.at(get_utc(11, 26)).do(fire_mbr, 2, random.choice(READY_MSGS), "Ready-First-MBR")
    schedule.every().day.at(get_utc(11, 28)).do(fire_mbr, 3, random.choice(READY_MSGS), "Ready-First-MBR")

    # ── Pre-first-signal Q&A — once per week (Monday only) ──────────────────
    schedule.every().monday.at(get_utc(11, 41)).do(
        fire_mbr, 1, random.choice(PRE_SIGNAL_QUESTIONS), "PreFirst-MBR")
    schedule.every().monday.at(get_utc(11, 43)).do(
        fire_mbr, 3, f"Signal at {_UK_FIRST} UK time today 🔔", "PreFirst-MBR")
    schedule.every().monday.at(get_utc(11, 46)).do(
        fire_mbr, 0, random.choice(PRE_SIGNAL_CONFIRMS), "PreFirst-MBR")

    # ── Post-first-signal reactions + "Done" (2 min apart each) ────────────
    schedule.every().day.at(get_utc(12,  2)).do(fire_mbr, 2, random.choice(SIGNAL_REACTIONS), "PostFirst-MBR")
    schedule.every().day.at(get_utc(12,  4)).do(fire_mbr, 1, random.choice(SIGNAL_REACTIONS), "PostFirst-MBR")
    schedule.every().day.at(get_utc(12,  6)).do(fire_mbr, 0, random.choice(SIGNAL_REACTIONS), "PostFirst-MBR")
    schedule.every().day.at(get_utc(12,  8)).do(fire_mbr, 3, random.choice(SIGNAL_REACTIONS), "PostFirst-MBR")
    schedule.every().day.at(get_utc(12, 10)).do(fire_mbr, 0, random.choice(DONE_MSGS), "Done-First-MBR")
    schedule.every().day.at(get_utc(12, 12)).do(fire_mbr, 1, random.choice(DONE_MSGS), "Done-First-MBR")
    schedule.every().day.at(get_utc(12, 14)).do(fire_mbr, 2, random.choice(DONE_MSGS), "Done-First-MBR")
    schedule.every().day.at(get_utc(12, 16)).do(fire_mbr, 3, random.choice(DONE_MSGS), "Done-First-MBR")

    # ── "Ready" before second signal lock (2 min apart each, lock at 13:30) ───
    schedule.every().day.at(get_utc(13, 22)).do(fire_mbr, 0, random.choice(READY_MSGS), "Ready-Second-MBR")
    schedule.every().day.at(get_utc(13, 24)).do(fire_mbr, 1, random.choice(READY_MSGS), "Ready-Second-MBR")
    schedule.every().day.at(get_utc(13, 26)).do(fire_mbr, 2, random.choice(READY_MSGS), "Ready-Second-MBR")
    schedule.every().day.at(get_utc(13, 28)).do(fire_mbr, 3, random.choice(READY_MSGS), "Ready-Second-MBR")

    # ── Pre-second-signal Q&A — once per week (Monday only) ─────────────────
    schedule.every().monday.at(get_utc(13, 41)).do(
        fire_mbr, 3, random.choice(PRE_SIGNAL_QUESTIONS), "PreSecond-MBR")
    schedule.every().monday.at(get_utc(13, 43)).do(
        fire_mbr, 2, f"Second signal at {_UK_SECOND} UK time 🔔", "PreSecond-MBR")
    schedule.every().monday.at(get_utc(13, 46)).do(
        fire_mbr, 1, random.choice(PRE_SIGNAL_CONFIRMS), "PreSecond-MBR")

    # ── Post-second-signal reactions + "Done" (2 min apart each) ───────────
    schedule.every().day.at(get_utc(14,  2)).do(fire_mbr, 0, random.choice(SIGNAL_REACTIONS), "PostSecond-MBR")
    schedule.every().day.at(get_utc(14,  4)).do(fire_mbr, 3, random.choice(SIGNAL_REACTIONS), "PostSecond-MBR")
    schedule.every().day.at(get_utc(14,  6)).do(fire_mbr, 2, random.choice(SIGNAL_REACTIONS), "PostSecond-MBR")
    schedule.every().day.at(get_utc(14,  8)).do(fire_mbr, 1, random.choice(SIGNAL_REACTIONS), "PostSecond-MBR")
    schedule.every().day.at(get_utc(14, 10)).do(fire_mbr, 0, random.choice(DONE_MSGS), "Done-Second-MBR")
    schedule.every().day.at(get_utc(14, 12)).do(fire_mbr, 1, random.choice(DONE_MSGS), "Done-Second-MBR")
    schedule.every().day.at(get_utc(14, 14)).do(fire_mbr, 2, random.choice(DONE_MSGS), "Done-Second-MBR")
    schedule.every().day.at(get_utc(14, 16)).do(fire_mbr, 3, random.choice(DONE_MSGS), "Done-Second-MBR")

    # ── Promo conversations — only within safe open windows ───────────────────
    # Conflicts avoided: lock at 3:30 AM, 11:30 AM, 1:30 PM, 5:00 PM (night)
    # Rule: session start + 90 min (max stagger+messages) must finish before lock
    #
    # Long open window (4:05 AM – 11:22 AM):
    #   → last safe start = 11:22 - 90min = 09:52 AM, so stop at 10:00 AM
    schedule.every().day.at(get_utc(4,  35)).do(fire_promo)   # 4:35 AM WAT
    schedule.every().day.at(get_utc(5,  45)).do(fire_promo)   # 5:45 AM WAT
    schedule.every().day.at(get_utc(7,   0)).do(fire_promo)   # 7:00 AM WAT
    schedule.every().day.at(get_utc(9,   0)).do(fire_promo)   # 9:00 AM WAT
    schedule.every().day.at(get_utc(10,  0)).do(fire_promo)   # 10:00 AM WAT (clears 11:22 ready by ~90min)
    #
    # Post-first-signal window (12:05 PM – 13:22 PM) = only 77 min — too tight, skipped
    #
    # Post-second-signal window (14:05 PM – 17:00 PM):
    #   → last safe start = 17:00 - 90min = 15:30 PM
    schedule.every().day.at(get_utc(14, 35)).do(fire_promo)   # 2:35 PM WAT
    schedule.every().day.at(get_utc(15, 30)).do(fire_promo)   # 3:30 PM WAT (finishes by ~4:40 PM ✓)

    # ── Afternoon general chat ────────────────────────────────────────────────
    schedule.every().day.at(get_utc(15, 30)).do(fire_mbr, 1, random.choice(GENERAL_MSGS), "General-MBR")

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


def _bare_id(raw: str) -> int:
    """Convert any group ID format to the bare positive int Telethon uses."""
    n = abs(int(raw.strip()))
    s = str(n)
    # Env vars or Bot-API IDs may have a "100" prefix (e.g. 1003257839303 or 1001234567890)
    # Telethon dialog.entity.id returns the bare positive ID without that prefix.
    if s.startswith("100") and len(s) > 12:
        n = int(s[3:])
    return n


async def resolve_groups():
    """
    Scan all account dialogs (main folder + archived folder) to find the
    3 configured groups + optional test group.
    Avoids get_entity() cache issues with StringSession.
    """
    global GROUPS, TEST_GROUP
    GROUPS.clear()
    TEST_GROUP = None

    # Build lookup: bare_id → raw string
    target_ids = {_bare_id(r): r.strip() for r in RAW_GROUPS}
    test_bare = _bare_id(TEST_GROUP_RAW)
    all_ids = {**target_ids, test_bare: TEST_GROUP_RAW}
    logger.info(f"[Startup] Looking for group IDs: {list(target_ids.keys())} + test={test_bare}")

    found = {}

    # Scan folder 0 (main inbox) then folder 1 (archived)
    for folder in (0, 1):
        if len(found) == len(all_ids):
            break
        label = "main inbox" if folder == 0 else "archived folder"
        logger.info(f"[Startup] Scanning {label}...")
        try:
            async for dialog in bot_client.iter_dialogs(folder=folder):
                eid = getattr(dialog.entity, 'id', None)
                if eid is not None and eid in all_ids:
                    found[eid] = dialog.entity
                    logger.info(
                        f"[Startup] ✓ Found '{dialog.title}' "
                        f"(id={eid}, folder={folder})"
                    )
                if len(found) == len(all_ids):
                    break
        except Exception as e:
            logger.warning(f"[Startup] Could not scan folder {folder}: {e}")

    # Populate the 3 main groups
    for n, raw in target_ids.items():
        if n in found:
            GROUPS.append(found[n])
        else:
            logger.error(
                f"[Startup] ✗ Group ID {raw} not found in any folder. "
                f"Is @cardon_js still a member/admin of this group?"
            )

    # Populate the test group
    if test_bare in found:
        TEST_GROUP = found[test_bare]
        logger.info(f"[Startup] ✓ Test group ready: '{TEST_GROUP.title}'")
    else:
        logger.warning(f"[Startup] ⚠ Test group (id={test_bare}) not found — /test-send will use main groups.")

    logger.info(f"[Startup] {len(GROUPS)}/3 main groups ready. Test group: {'✓' if TEST_GROUP else '✗'}")


async def start_bot():
    global bot_client
    bot_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await bot_client.connect()
    if not await bot_client.is_user_authorized():
        logger.error("Session not authorized! Visit the web URL to re-authenticate.")
        return
    me = await bot_client.get_me()
    global PROFESSOR_ID
    PROFESSOR_ID = me.id
    logger.info(f"=== PROFESSOR online as: {me.first_name} (@{me.username}) (ID={PROFESSOR_ID}) ===")

    await resolve_groups()

    if not GROUPS:
        logger.error("[Startup] FATAL: 0 groups resolved. Bot will not send or lock anything.")
        return

    # Quick connectivity test — log group titles
    for g in GROUPS:
        logger.info(f"[Startup] Ready to operate in: '{g.title}'")

    # Start member bots (non-fatal — bot works fine without them)
    try:
        await start_member_bots()
    except Exception as e:
        logger.error(f"[MemberBots] Startup error: {e}")

    # Catch up on any jobs missed while the bot was restarting
    await catch_up_on_startup()

    sched_thread = threading.Thread(target=run_scheduler, daemon=True)
    sched_thread.start()
    await bot_client.run_until_disconnected()


def keep_alive():
    """
    Ping own /ping endpoint every 8 minutes so Render never spins the service down.
    Also logs the heartbeat so we can confirm the bot is alive in the logs.
    """
    self_url  = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{PORT}").rstrip("/")
    ping_url  = f"{self_url}/ping"
    interval  = 480  # 8 minutes — well within Render's 15-min idle timeout
    logger.info(f"[KeepAlive] Starting — pinging {ping_url} every {interval}s")
    while True:
        time_mod.sleep(interval)
        try:
            urllib.request.urlopen(ping_url, timeout=10)
            logger.info("[KeepAlive] ✓ Heartbeat OK")
        except Exception as e:
            logger.warning(f"[KeepAlive] ✗ Ping failed: {e}")


if __name__ == "__main__":
    if SESSION_STRING:
        asyncio.run_coroutine_threadsafe(start_bot(), _loop)
        logger.info("Bot started in background loop.")

    # Start keep-alive pinger
    ka_thread = threading.Thread(target=keep_alive, daemon=True)
    ka_thread.start()

    logger.info(f"Starting web server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)
