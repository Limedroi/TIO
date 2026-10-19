"""Tio - Talk It Out! (Telegram anonymous support / confession bot)

Install: pip install "python-telegram-bot>=20.7" python-dotenv
Run:    BOT_TOKEN=123:ABC python tio_bot_updated.py

Required bot permissions:
- Admin group: send messages; BACKUP group: send documents, pin and delete messages.
- Channel: post messages.

Persistence:
- tio_data.json and users_settings.json are stored together in the ZIP backup.
- Existing backups containing only tio_data.json are migrated on restore.
- Five owner-provided moderator IDs are built in. ADMIN_IDS can add more IDs via
  a comma-separated environment variable; once IDs are configured, moderation is allowlisted.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import io
import json
import logging
import math
import os
import re
import time
import zipfile
from typing import Any

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ChatType, ParseMode
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set. Put it in the environment or a .env file.")

ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-5370857010"))
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1004439548910"))
BACKUP_GROUP_ID = int(os.environ.get("BACKUP_GROUP_ID", "-5044416482"))
BACKUP_DELAY = int(os.environ.get("BACKUP_DELAY", "60"))
CONFESSION_COOLDOWN_SECONDS = int(os.environ.get("CONFESSION_COOLDOWN_SECONDS", "1800"))
FLOOD_WINDOW_SECONDS = int(os.environ.get("FLOOD_WINDOW_SECONDS", "600"))
FLOOD_MAX_SUBMISSIONS = int(os.environ.get("FLOOD_MAX_SUBMISSIONS", "5"))
DUPLICATE_WINDOW_SECONDS = int(os.environ.get("DUPLICATE_WINDOW_SECONDS", "600"))
DEFAULT_ADMIN_IDS = {
    2112316128,
    5131223597,
    5879238618,
    940770584,
    1673629248,
}
ADMIN_IDS = DEFAULT_ADMIN_IDS | {
    int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

MAX_LEN = 3000
REPLY_RE = re.compile(r"^\s*[Tt](\d+)\s*(.*)$", re.DOTALL)
NUMBER_RE = re.compile(r"^\s*[Tt]?\s*(\d+)\s*$")
BACKUP_JSON_NAME = "tio_data.json"
SETTINGS_JSON_NAME = "users_settings.json"

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("tio")

# ---------------------------------------------------------------------------
# UI text and buttons
GENDER_OPTIONS = [("👨 ولد", "ولد"), ("👩 بنت", "بنت")]
CLASS_OPTIONS = [("دفعة 44", "44"), ("دفعة 45", "45")]
GROUPS = [f"G{i}" for i in range(1, 10)]
BTN_HIDDEN_GROUP = "🤐 مفضلش أقول"
BTN_ALLOW_REPLIES = "✅ اسمح"
BTN_DENY_REPLIES = "🚫 متسمحش"
BTN_APPROVE = "✅ موافقة"
BTN_REJECT = "❌ رفض"

HOME_WRITE = "✍️ فضفض"
HOME_MYTALK = "💌 MyTalk"
HOME_PRIVACY = "🔒 الخصوصية"
HOME_HELP = "❔ مساعدة"

TXT_WELCOME = (
    "أهلاً بيك في *Tio — Talk It Out!* 👋\n"
    "مكان تقدر تفضفض فيه براحتك.\n\n"
    "أولًا، تحب بيانات إيه تظهر مع اعترافك؟\n"
    "🔒 *مجهول تمامًا* هو الاختيار الافتراضي والأكثر خصوصية. "
    "البيانات دي مش بتظهر لباقي المستخدمين إلا لو اخترت إظهارها."
)
TXT_ASK_GENDER = "تحب يظهر إيه في بياناتك العامة؟ اختار النوع:"
TXT_ASK_CLASS = "إنت في أنهي دفعة؟"
TXT_ASK_GROUP = "إنت في أنهي جروب؟"
TXT_ASK_REPLIES = (
    "تحب تسمح بالردود الخاصة على اعترافاتك؟\n"
    "الردود بتوصلك من خلال البوت، ومش بتكشف هويتك للطرف التاني."
)
TXT_SETUP_DONE = "🎉 كده تمام! استخدم الأزرار تحت عشان تفضفض أو تتابع محادثاتك."
TXT_HOME = "أهلاً بيك في *Tio — Talk It Out!* 👋\nفضفض براحتك. إحنا سامعينك."
TXT_NEED_START = "اضغط /start الأول عشان تظبط إعداداتك."
TXT_CONFESSION_RECEIVED = "✅ اعترافك اتسجل برقم *T{cid}* وبيستنى المراجعة. تقدر تتابع حالته من MyTalk."
TXT_ASK_REPLY_TEXT = "✍️ ابعت ردك على T{cid} دلوقتي (أو /cancel)."
TXT_CONFESSION_NOT_FOUND = "❌ الاعتراف T{cid} مش موجود أو لسه مش منشور."
TXT_REPLIES_DISABLED = "🚫 صاحب T{cid} مش سامح بالردود الخاصة."
TXT_OWN_CONFESSION = "مينفعش ترد على اعترافك إنت 🙂"
TXT_REPLY_SENT_FOR_REVIEW = "✅ ردك على T{cid} اتبعت للمراجعة. لو اتوافق عليه، هتبدأ محادثة مجهولة تقدروا تكملوا فيها."
TXT_CONVERSATION_DELIVERED = "✅ رسالتك المجهولة اتبعتت للطرف التاني. تقدروا تكملوا الكلام من MyTalk."
TXT_CONVERSATION_DELIVERY_FAILED = "⚠️ مقدرتش أوصل الرسالة للطرف التاني دلوقتي. جرّب تبعتها تاني من MyTalk."
TXT_CANCELLED = "اتلغى."
TXT_ASK_REPLY_NUMBER = "🔢 ابعت رقم الاعتراف اللي عايز ترد عليه (مثلاً T5 أو 5)."
TXT_BAD_NUMBER = "❌ الرقم مش مظبوط. ابعت رقم الاعتراف (مثلاً T5 أو 5) أو /cancel."
TXT_TOO_LONG = "❌ الرسالة طويلة قوي. الحد الأقصى {max} حرف."
TXT_SUSPENDED = "🚫 مش هتقدر تبعت رسائل جديدة حاليًا. انتهاء الإيقاف: {until}. لو شايف إن ده خطأ، تواصل مع إدارة البوت."
TXT_COOLDOWN = "⏳ تقدر تبعت اعتراف جديد بعد {minutes} دقيقة تقريبًا. تقدر في الوقت ده تتابع MyTalk أو ترد على محادثاتك."
TXT_FLOOD = "⏳ الرسائل كتير بسرعة. استنى شوية وجرب تاني."
TXT_DUPLICATE = "⚠️ الرسالة دي شبه رسالة بعتها قريب. عدّلها أو استنى شوية قبل إعادة إرسالها."
TXT_PRIVACY = (
    "🔒 *إعدادات الخصوصية*\n\n"
    "طريقة عرض الهوية: *{identity}*\n"
    "الردود الخاصة على اعترافاتك: *{replies}*\n\n"
    "المجهول هنا معناه إن المستخدمين التانيين مش هيشوفوا بياناتك. "
    "إدارة البوت تقدر تقنيًا تربط الرسائل بحساب تيليجرام لمعالجة البلاغات والإساءة. "
    "ما تبعتش بيانات حساسة أو معلومات تكشف هويتك."
)
TXT_HELP = (
    "*Tio — مساعدة سريعة*\n\n"
    "✍️ فضفض: ابعت اعتراف جديد للمراجعة.\n"
    "💌 MyTalk: شوف اعترافاتك المنشورة أو اللي لسه تحت المراجعة، ومحادثاتك المجهولة.\n"
    "/reply T5 — ابعت رد مجهول على اعتراف منشور.\n"
    "المحادثة الخاصة بعد بداية التواصل مش بتخضع لمراجعة مسبقة؛ لو حصل بلاغ، الإدارة هتراجع سجل المحادثة.\n"
    "/settings — غيّر الخصوصية والسماح بالردود.\n"
    "/cancel — ألغِ كتابة رد أو رسالة.\n\n"
    "الاعترافات والرد الأول بتخضع للمراجعة. Tio مش خدمة طوارئ أو بديل عن المساعدة المتخصصة."
)
TXT_REPORT_SENT = "🚩 البلاغ اتبعت للمراجعة. شكرًا إنك ساعدت في الحفاظ على مساحة آمنة."
TXT_REPORT_DUPLICATE = "البلاغ ده موجود بالفعل عند الإدارة للمراجعة."
TXT_CONV_CLOSED = "المحادثة دي اتقفلت ومش هتقدر تبعت فيها رسائل جديدة."

TXT_CONF_APPROVED_PUBLISHED = "✅ اعترافك T{cid} اتوافق عليه واتنشر."
TXT_CONF_REJECTED = None
TXT_REPLY_DELIVERED_TO_SENDER = "✅ ردك على T{cid} اتوافق عليه، وبدأت محادثة مجهولة. تقدر تكمل من MyTalk."
TXT_REPLY_REJECTED_TO_SENDER = None

TXT_ADMIN_NEW_CONFESSION = (
    "📩 <b>اعتراف جديد T{cid}</b>\n"
    "<i>{label} • الردود {replies} • UID <code>{uid}</code></i>\n\n{text}"
)
TXT_REPLIES_ON = "شغالة"
TXT_REPLIES_OFF = "مقفولة"
TXT_ADMIN_NEW_REPLY = (
    "💬 <b>رد R{rid} ← T{cid}</b>\n"
    "<i>من: {label} • UID <code>{uid}</code></i>\n\n"
    "<b>الاعتراف الأصلي:</b> {original}\n\n"
    "<b>الرد:</b> {text}"
)
TXT_ADMIN_NEW_CONV_MESSAGE = (
    "🗨️ <b>رسالة محادثة مجهولة M{mid}</b>\n"
    "<i>المحادثة C{conv_id} • T{cid} • UID <code>{uid}</code></i>\n\n{text}"
)
TXT_VERDICT_APPROVED = "✅ تمت الموافقة"
TXT_VERDICT_REJECTED = "❌ اترفض"
TXT_VERDICT_LINE = "<b>{verdict}</b> بواسطة {admin}"
TXT_NOT_ADMIN_GROUP = "مش مسموحلك."
TXT_ALREADY_HANDLED = "اتعالج قبل كده."
TXT_OK_TOAST = "تمام"
TXT_CHANNEL_FAIL_WARNING = "⚠️ معرفتش أنشر T{cid}. الاعتراف لسه في انتظار المراجعة؛ جرّب الموافقة تاني بعد حل المشكلة."

TXT_CHANNEL_POST = "<b>T{cid}</b>\n<i>{label}</i>\n\n{text}"
TXT_CHANNEL_REPLY_HINT = "\n\nلو عايز ترد عليه بشكل مجهول استخدم /reply <code>T{cid}</code>"
TXT_CHANNEL_FOOTER = (
    "\n\n<blockquote>البوت: @TIO44_bot</blockquote>"
    "\n<blockquote>القناة: https://t.me/TalkItOut_Channel</blockquote>"
)
LABEL_FORMAT = "{gender} • دفعة {cls} • {grp}"
LABEL_HIDDEN_GROUP = "الجروب مخفي"

COMMANDS = [
    ("start", "ابدأ أو افتح القائمة الرئيسية"),
    ("mytalk", "اعترافاتك ومحادثاتك"),
    ("reply", "رد على اعتراف منشور"),
    ("settings", "إعدادات الخصوصية"),
    ("help", "مساعدة"),
    ("cancel", "إلغاء العملية الحالية"),
]

# ---------------------------------------------------------------------------
# Runtime state. Preferences are separated into users_settings.json in backups.
state: dict[str, Any] = {
    "users": {},
    "confessions": {},
    "replies": {},
    "conversations": {},
    "conversation_messages": {},
    "reports": {},
    "next_confession": 1,
    "next_reply": 1,
    "next_conversation": 1,
    "next_conversation_message": 1,
    "next_report": 1,
}
meta: dict[str, Any] = {"dirty_since": None, "last_backup_msg": None, "lock": None}

PREFERENCE_KEYS = ("gender", "class", "grp", "allow_replies", "identity_mode")
BASE_USER_KEYS = ("user_id", "last_confession_at", "submission_events", "suspended_until", "suspend_reason")


def mark_dirty() -> None:
    if meta["dirty_since"] is None:
        meta["dirty_since"] = time.monotonic()


def load_state(raw: bytes, settings_raw: bytes | None = None) -> None:
    """Load current or legacy state, then merge the preferences sidecar."""
    loaded = json.loads(raw)
    defaults = {
        "users": {}, "confessions": {}, "replies": {}, "conversations": {},
        "conversation_messages": {}, "reports": {}, "next_confession": 1,
        "next_reply": 1, "next_conversation": 1, "next_conversation_message": 1,
        "next_report": 1,
    }
    for key, default in defaults.items():
        value = loaded.get(key, default)
        if key in ("users", "confessions", "replies", "conversations", "conversation_messages", "reports"):
            state[key] = {int(k): v for k, v in value.items()}
        else:
            state[key] = value

    sidecar: dict[int, dict[str, Any]] = {}
    if settings_raw:
        try:
            parsed = json.loads(settings_raw)
            sidecar = {int(k): v for k, v in parsed.items()}
        except (json.JSONDecodeError, TypeError, ValueError):
            log.exception("users_settings.json was unreadable; migrating settings from tio_data.json")

    # Migrate legacy embedded preferences. New sidecar values take precedence.
    for uid, user in state["users"].items():
        legacy = {k: user[k] for k in PREFERENCE_KEYS if k in user}
        merged_preferences = dict(legacy)
        merged_preferences.update(sidecar.get(uid, {}))
        user.update(merged_preferences)
        user.setdefault("user_id", uid)
        user.setdefault("identity_mode", "anonymous")
        user.setdefault("allow_replies", None)
        user.setdefault("submission_events", [])
        user.setdefault("suspended_until", 0)
        user.setdefault("suspend_reason", "")
        user.pop("username", None)
        user.pop("name", None)
    # Preferences sidecar can contain a user absent from the base data.
    for uid, prefs in sidecar.items():
        user = state["users"].setdefault(uid, {"user_id": uid, "submission_events": [], "suspended_until": 0})
        user.update(prefs)
        user.setdefault("identity_mode", "anonymous")
        user.setdefault("allow_replies", None)

    # Protect counters if restoring a slightly older backup.
    for key, coll in (("next_confession", "confessions"), ("next_reply", "replies"),
                      ("next_conversation", "conversations"),
                      ("next_conversation_message", "conversation_messages"),
                      ("next_report", "reports")):
        state[key] = max(int(state.get(key, 1)), max(state[coll].keys(), default=0) + 1)


def persisted_state_and_settings() -> tuple[dict[str, Any], dict[str, Any]]:
    base = {k: v for k, v in state.items() if k != "users"}
    base["users"] = {}
    settings: dict[str, Any] = {}
    for uid, user in state["users"].items():
        base["users"][str(uid)] = {k: user[k] for k in BASE_USER_KEYS if k in user}
        settings[str(uid)] = {k: user[k] for k in PREFERENCE_KEYS if k in user}
    return base, settings


async def flush_backup(bot) -> None:
    async with meta["lock"]:
        if meta["dirty_since"] is None:
            return
        base, settings = persisted_state_and_settings()
        main_payload = json.dumps(base, ensure_ascii=False, indent=1).encode("utf-8")
        settings_payload = json.dumps(settings, ensure_ascii=False, indent=1).encode("utf-8")
        counts = {
            "users": len(state["users"]), "confessions": len(state["confessions"]),
            "replies": len(state["replies"]), "conversations": len(state["conversations"]),
        }
        meta["dirty_since"] = None
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(BACKUP_JSON_NAME, main_payload)
            zf.writestr(SETTINGS_JSON_NAME, settings_payload)
        buf.seek(0)
        filename = f"tio_backup_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.zip"
        try:
            msg = await bot.send_document(
                BACKUP_GROUP_ID, document=InputFile(buf, filename=filename),
                caption=(f"🗂 نسخة احتياطية\n👥 مستخدمين: {counts['users']}\n"
                         f"📩 اعترافات: {counts['confessions']}\n💬 ردود: {counts['replies']}\n"
                         f"🗨️ محادثات: {counts['conversations']}"),
                disable_notification=True,
            )
            await bot.pin_chat_message(BACKUP_GROUP_ID, msg.message_id, disable_notification=True)
        except RetryAfter as e:
            meta["dirty_since"] = time.monotonic() - BACKUP_DELAY + e.retry_after + 1
            raise
        except Exception:
            meta["dirty_since"] = time.monotonic()
            raise
        old = meta["last_backup_msg"]
        meta["last_backup_msg"] = msg.message_id
        if old and old != msg.message_id:
            try:
                await bot.delete_message(BACKUP_GROUP_ID, old)
            except TelegramError as e:
                log.warning("Couldn't delete old backup: %s", e)


async def backup_loop(bot) -> None:
    while True:
        await asyncio.sleep(1)
        since = meta["dirty_since"]
        if since is None or time.monotonic() - since < BACKUP_DELAY:
            continue
        try:
            await flush_backup(bot)
            log.info("Backup sent.")
        except Exception as e:
            log.error("Backup failed (will retry): %s", e)


async def restore_from_pinned(bot) -> None:
    chat = await bot.get_chat(BACKUP_GROUP_ID)
    pm = chat.pinned_message
    if not pm or not pm.document or not (pm.document.file_name or "").endswith(".zip"):
        log.info("No pinned backup found - starting fresh.")
        return
    tg_file = await pm.document.get_file()
    data = bytes(await tg_file.download_as_bytearray())
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        main_raw = zf.read(BACKUP_JSON_NAME)
        settings_raw = zf.read(SETTINGS_JSON_NAME) if SETTINGS_JSON_NAME in zf.namelist() else None
        load_state(main_raw, settings_raw)
    meta["last_backup_msg"] = pm.message_id
    log.info("Restored %d users, %d confessions, %d conversations",
             len(state["users"]), len(state["confessions"]), len(state["conversations"]))


async def on_start(app: Application) -> None:
    meta["lock"] = asyncio.Lock()
    await restore_from_pinned(app.bot)
    try:
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])
    except TelegramError as e:
        log.warning("Couldn't set commands: %s", e)
    app.bot_data["backup_task"] = asyncio.create_task(backup_loop(app.bot))


async def on_stop(app: Application) -> None:
    task = app.bot_data.get("backup_task")
    if task:
        task.cancel()
    if meta["dirty_since"] is not None:
        try:
            await flush_backup(app.bot)
        except Exception as e:
            log.error("Final backup failed: %s", e)

# ---------------------------------------------------------------------------
# Helpers

def esc(value: str) -> str:
    return html.escape(value or "", quote=False)


def stored_html(item: dict[str, Any]) -> str:
    return item.get("html") or esc(item.get("text", ""))


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text, callback_data=data) for text, data in row]
        for row in rows
    ])


def home_markup() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(HOME_WRITE), KeyboardButton(HOME_MYTALK)],
         [KeyboardButton(HOME_PRIVACY), KeyboardButton(HOME_HELP)]],
        resize_keyboard=True, is_persistent=True,
    )


def get_user(uid: int) -> dict[str, Any] | None:
    return state["users"].get(uid)


def touch_user(tg_user) -> dict[str, Any]:
    uid = tg_user.id
    u = state["users"].get(uid)
    if u is None:
        # A new user chooses anonymous (recommended) or a public demographic label.
        u = {"user_id": uid, "identity_mode": None, "allow_replies": None,
             "submission_events": [], "suspended_until": 0, "suspend_reason": ""}
        state["users"][uid] = u
        mark_dirty()
    else:
        changed = False
        for key, value in (("user_id", uid), ("identity_mode", "anonymous"),
                           ("allow_replies", None), ("submission_events", []),
                           ("suspended_until", 0), ("suspend_reason", "")):
            if key not in u:
                u[key] = value
                changed = True
        # Names and usernames are not needed for Tio's operation, so do not retain them.
        if "username" in u or "name" in u:
            u.pop("username", None)
            u.pop("name", None)
            changed = True
        if changed:
            mark_dirty()
    return u


def profile_complete(u: dict[str, Any] | None) -> bool:
    if not u or u.get("identity_mode") not in ("anonymous", "label"):
        return False
    if u.get("allow_replies") is None:
        return False
    if u.get("identity_mode") == "anonymous":
        return True
    return bool(u.get("gender") and u.get("class") and u.get("grp"))


def label(u: dict[str, Any] | None) -> str:
    if not u or u.get("identity_mode", "anonymous") == "anonymous":
        return "مجهول"
    if not (u.get("gender") and u.get("class") and u.get("grp")):
        return "مجهول"
    grp = LABEL_HIDDEN_GROUP if u["grp"] == "Hidden" else u["grp"]
    return LABEL_FORMAT.format(gender=u["gender"], cls=u["class"], grp=grp)


async def send_home(bot, uid: int, text: str = TXT_HOME) -> None:
    await bot.send_message(uid, text, parse_mode=ParseMode.MARKDOWN, reply_markup=home_markup())


async def safe_send(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str | None,
                    html_mode: bool = False, reply_markup=None) -> bool:
    if not text:
        return True
    try:
        await ctx.bot.send_message(
            chat_id, text, parse_mode=ParseMode.HTML if html_mode else None,
            reply_markup=reply_markup,
        )
        return True
    except Exception as e:
        log.warning("Could not message %s: %s", chat_id, e)
        return False


def identity_keyboard():
    return kb([[("🔒 مجهول تمامًا (أنسب للخصوصية)", "im:anonymous")],
               [("🏷️ إظهار بيانات عامة", "im:label")]])


async def continue_setup(bot, uid: int, u: dict[str, Any], edit_query=None) -> None:
    text = None
    markup = None
    if u.get("identity_mode") == "label":
        if not u.get("gender"):
            text = TXT_ASK_GENDER
            markup = kb([[(t, f"g:{v}") for t, v in GENDER_OPTIONS]])
        elif not u.get("class"):
            text = TXT_ASK_CLASS
            markup = kb([[(t, f"c:{v}") for t, v in CLASS_OPTIONS]])
        elif not u.get("grp"):
            rows = [[(g, f"grp:{g}") for g in GROUPS[i:i + 3]] for i in range(0, len(GROUPS), 3)]
            rows.append([(BTN_HIDDEN_GROUP, "grp:Hidden")])
            text, markup = TXT_ASK_GROUP, kb(rows)
    if text is None and u.get("allow_replies") is None:
        text = TXT_ASK_REPLIES
        markup = kb([[(BTN_ALLOW_REPLIES, "pr:1"), (BTN_DENY_REPLIES, "pr:0")]])
    if text is None and profile_complete(u):
        await send_home(bot, uid)
        return
    if edit_query is not None:
        await edit_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN if "*" in text else None,
                                           reply_markup=markup)
    else:
        await bot.send_message(uid, text, parse_mode=ParseMode.MARKDOWN if "*" in text else None,
                               reply_markup=markup)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    u = touch_user(update.effective_user)
    # /start no longer resets preferences or profile fields.
    ctx.user_data.pop("awaiting_number", None)
    ctx.user_data.pop("reply_to", None)
    ctx.user_data.pop("conversation_reply_to", None)
    ctx.user_data.pop("compose_confession", None)
    if profile_complete(u):
        await update.message.reply_text(TXT_HOME, parse_mode=ParseMode.MARKDOWN, reply_markup=home_markup())
    elif u.get("identity_mode") not in ("anonymous", "label"):
        await update.message.reply_text(TXT_WELCOME, parse_mode=ParseMode.MARKDOWN,
                                        reply_markup=identity_keyboard())
    else:
        await continue_setup(ctx.bot, update.effective_user.id, u)


async def onboarding_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    u = touch_user(q.from_user)
    kind, _, val = q.data.partition(":")
    if kind == "im":
        u["identity_mode"] = val
        mark_dirty()
        if val == "anonymous":
            await continue_setup(ctx.bot, q.from_user.id, u, q)
        else:
            await continue_setup(ctx.bot, q.from_user.id, u, q)
    elif kind == "g":
        u["gender"] = val
        mark_dirty()
        await continue_setup(ctx.bot, q.from_user.id, u, q)
    elif kind == "c":
        u["class"] = val
        mark_dirty()
        await continue_setup(ctx.bot, q.from_user.id, u, q)
    elif kind == "grp":
        u["grp"] = val
        mark_dirty()
        await continue_setup(ctx.bot, q.from_user.id, u, q)
    elif kind == "pr":
        u["allow_replies"] = int(val)
        mark_dirty()
        await q.edit_message_text(TXT_SETUP_DONE)
        await send_home(ctx.bot, q.from_user.id)

# ---------------------------------------------------------------------------
# Privacy settings and home menu
async def send_settings(bot, uid: int) -> None:
    u = get_user(uid)
    if not u:
        await bot.send_message(uid, TXT_NEED_START)
        return
    identity_text = "مجهول تمامًا" if u.get("identity_mode") != "label" else "بيانات عامة"
    replies_text = "مسموح" if u.get("allow_replies") else "مقفول"
    text = TXT_PRIVACY.format(identity=identity_text, replies=replies_text)
    markup = kb([
        [("🔒 مجهول تمامًا", "privacy:anonymous"), ("🏷️ بيانات عامة", "privacy:label")],
        [("✅ السماح بالردود", "replies:1"), ("🚫 منع الردود", "replies:0")],
        [("🏠 الرئيسية", "settings:home")],
    ])
    await bot.send_message(uid, text, parse_mode=ParseMode.MARKDOWN, reply_markup=markup)


async def settings_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q.message.chat.type != ChatType.PRIVATE:
        await q.answer("استخدم الإعدادات في الخاص مع البوت.", show_alert=True)
        return
    await q.answer()
    u = touch_user(q.from_user)
    kind, _, val = q.data.partition(":")
    if kind == "privacy":
        u["identity_mode"] = val
        mark_dirty()
        if val == "label" and not (u.get("gender") and u.get("class") and u.get("grp")):
            await q.edit_message_text("علشان تعرض بيانات عامة، اختار البيانات اللي حابب تظهر. تقدر ترجع للمجهول في أي وقت.")
            await continue_setup(ctx.bot, q.from_user.id, u)
            return
        await q.edit_message_text("✅ تم تحديث إعدادات الخصوصية.")
        await send_settings(ctx.bot, q.from_user.id)
    elif kind == "replies":
        u["allow_replies"] = int(val)
        mark_dirty()
        await q.edit_message_text("✅ تم تحديث إعدادات الردود.")
        await send_settings(ctx.bot, q.from_user.id)
    elif kind == "settings" and val == "open":
        await q.edit_message_text("فتحت إعدادات الخصوصية.")
        await send_settings(ctx.bot, q.from_user.id)
    elif kind == "settings" and val == "home":
        await q.edit_message_text("رجعناك للقائمة الرئيسية. استخدم أزرار القائمة تحت.")
        await send_home(ctx.bot, q.from_user.id)

# ---------------------------------------------------------------------------
# Submission safety: suspension, cooldown, flood control, duplicate detection

def suspension_error(uid: int) -> str | None:
    u = get_user(uid)
    if not u:
        return None
    until = float(u.get("suspended_until") or 0)
    if until > time.time():
        return TXT_SUSPENDED.format(until=time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(until)))
    return None


def normalized_hash(text: str) -> str:
    normalized = " ".join(text.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def check_submission(uid: int, text: str, kind: str) -> str | None:
    u = get_user(uid)
    if not u:
        return TXT_NEED_START
    suspended = suspension_error(uid)
    if suspended:
        return suspended
    now = time.time()
    if kind == "confession":
        last_confession = float(u.get("last_confession_at") or 0)
        if now - last_confession < CONFESSION_COOLDOWN_SECONDS:
            remaining = CONFESSION_COOLDOWN_SECONDS - (now - last_confession)
            return TXT_COOLDOWN.format(minutes=max(1, math.ceil(remaining / 60)))
    events = [e for e in u.get("submission_events", [])
              if isinstance(e, dict) and now - float(e.get("at", 0)) <= max(FLOOD_WINDOW_SECONDS, DUPLICATE_WINDOW_SECONDS)]
    u["submission_events"] = events
    if len([e for e in events if now - float(e.get("at", 0)) <= FLOOD_WINDOW_SECONDS]) >= FLOOD_MAX_SUBMISSIONS:
        return TXT_FLOOD
    digest = normalized_hash(text)
    if any(e.get("kind") == kind and e.get("hash") == digest
           and now - float(e.get("at", 0)) <= DUPLICATE_WINDOW_SECONDS for e in events):
        return TXT_DUPLICATE
    return None


def record_submission(uid: int, text: str, kind: str) -> None:
    u = get_user(uid)
    if not u:
        return
    now = time.time()
    u.setdefault("submission_events", []).append({"at": now, "hash": normalized_hash(text), "kind": kind})
    cutoff = now - max(FLOOD_WINDOW_SECONDS, DUPLICATE_WINDOW_SECONDS)
    u["submission_events"] = [e for e in u["submission_events"] if float(e.get("at", 0)) >= cutoff]
    mark_dirty()


def reply_target_error(sender: int, cid: int) -> str | None:
    conf = state["confessions"].get(cid)
    if not conf or conf.get("status") != "approved":
        return TXT_CONFESSION_NOT_FOUND.format(cid=cid)
    owner = get_user(conf["user_id"])
    if not owner or not owner.get("allow_replies"):
        return TXT_REPLIES_DISABLED.format(cid=cid)
    if conf["user_id"] == sender:
        return TXT_OWN_CONFESSION
    return None


async def begin_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE, cid: int) -> None:
    err = reply_target_error(update.effective_user.id, cid)
    if err:
        await update.message.reply_text(err)
        return
    suspended = suspension_error(update.effective_user.id)
    if suspended:
        await update.message.reply_text(suspended)
        return
    ctx.user_data["reply_to"] = cid
    ctx.user_data.pop("conversation_reply_to", None)
    await update.message.reply_text(TXT_ASK_REPLY_TEXT.format(cid=cid))


async def reply_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    if not profile_complete(get_user(update.effective_user.id)):
        await update.message.reply_text(TXT_NEED_START)
        return
    ctx.user_data.pop("reply_to", None)
    ctx.user_data.pop("awaiting_number", None)
    if ctx.args:
        m = NUMBER_RE.match(" ".join(ctx.args))
        if m:
            await begin_reply(update, ctx, int(m.group(1)))
            return
    ctx.user_data["awaiting_number"] = True
    await update.message.reply_text(TXT_ASK_REPLY_NUMBER)


async def submit_confession(update: Update, ctx: ContextTypes.DEFAULT_TYPE, u: dict[str, Any],
                            plain: str, formatted: str) -> None:
    uid = update.effective_user.id
    if not plain:
        await update.message.reply_text("ابعت نص الاعتراف الأول، أو /cancel للإلغاء.")
        return
    if len(plain) > MAX_LEN:
        await update.message.reply_text(TXT_TOO_LONG.format(max=MAX_LEN))
        return
    now = time.time()
    # The 30-minute cooldown applies to new confessions, not ordinary replies.
    error = check_submission(uid, plain, "confession")
    if error:
        await update.message.reply_text(error)
        return
    cid = state["next_confession"]
    state["next_confession"] += 1
    state["confessions"][cid] = {
        "id": cid, "user_id": uid, "text": plain, "html": formatted,
        "status": "pending", "created": now,
    }
    u["last_confession_at"] = now
    record_submission(uid, plain, "confession")
    mark_dirty()
    try:
        await ctx.bot.send_message(
            ADMIN_GROUP_ID,
            TXT_ADMIN_NEW_CONFESSION.format(
                cid=cid, label=esc(label(u)), text=formatted,
                replies=TXT_REPLIES_ON if u.get("allow_replies") else TXT_REPLIES_OFF,
                uid=uid,
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=kb([[(BTN_APPROVE, f"ac:{cid}"), (BTN_REJECT, f"rc:{cid}")]]),
        )
    except TelegramError:
        # Keep the pending item; an admin is explicitly alerted so it isn't stranded silently.
        log.exception("Could not send confession T%s to moderation group", cid)
        await update.message.reply_text("⚠️ الاعتراف اتسجل، لكن حصلت مشكلة في إرساله للمراجعة. الإدارة اتبلغت في سجل البوت.")
        return
    await update.message.reply_text(TXT_CONFESSION_RECEIVED.format(cid=cid), parse_mode=ParseMode.MARKDOWN)


async def submit_reply(update: Update, cid: int, plain: str, formatted: str) -> None:
    uid = update.effective_user.id
    err = reply_target_error(uid, cid)
    if err:
        await update.message.reply_text(err)
        return
    if not plain:
        await update.message.reply_text("ابعت نص الرد، أو /cancel للإلغاء.")
        return
    if len(plain) > MAX_LEN:
        await update.message.reply_text(TXT_TOO_LONG.format(max=MAX_LEN))
        return
    error = check_submission(uid, plain, "reply")
    if error:
        await update.message.reply_text(error)
        return
    conf = state["confessions"][cid]
    rid = state["next_reply"]
    state["next_reply"] += 1
    state["replies"][rid] = {
        "id": rid, "confession_id": cid, "from_user": uid,
        "text": plain, "html": formatted, "status": "pending", "created": time.time(),
    }
    record_submission(uid, plain, "reply")
    mark_dirty()
    try:
        await update.get_bot().send_message(
            ADMIN_GROUP_ID,
            TXT_ADMIN_NEW_REPLY.format(
                rid=rid, cid=cid, label=esc(label(get_user(uid))), uid=uid,
                original=esc(conf.get("text", "")[:300]) + ("…" if len(conf.get("text", "")) > 300 else ""),
                text=formatted,
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=kb([[(BTN_APPROVE, f"ar:{rid}"), (BTN_REJECT, f"rr:{rid}")]]),
        )
    except TelegramError:
        log.exception("Could not send reply R%s to moderation group", rid)
        await update.message.reply_text("⚠️ الرد اتسجل لكن تعذر إرساله للمراجعة. حاول تتواصل مع الإدارة.")
        return
    await update.message.reply_text(TXT_REPLY_SENT_FOR_REVIEW.format(cid=cid))

# ---------------------------------------------------------------------------
# Anonymous two-way conversations

def conversation_keyboard(conv_id: int, message_id: int | None = None, include_reply: bool = True):
    rows: list[list[tuple[str, str]]] = []
    if include_reply:
        rows.append([("↩️ رد مجهول", f"convreply:{conv_id}")])
    report_row: list[tuple[str, str]] = []
    if message_id is not None:
        report_row.append(("🚩 إبلاغ عن الرسالة", f"reportmsg:{message_id}"))
    report_row.append(("🚩 إبلاغ عن المحادثة", f"reportconv:{conv_id}"))
    rows.append(report_row)
    rows.append([("⏹️ إنهاء المحادثة", f"closeconv:{conv_id}")])
    return kb(rows)


def get_conversation(cid: int) -> dict[str, Any] | None:
    return state["conversations"].get(cid)


def conversation_other(conv: dict[str, Any], uid: int) -> int | None:
    if uid == conv.get("user_a"):
        return conv.get("user_b")
    if uid == conv.get("user_b"):
        return conv.get("user_a")
    return None


def create_conversation_for_reply(reply: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create once, so retrying a failed delivery doesn't create duplicate threads."""
    conf = state["confessions"][reply["confession_id"]]
    conv_id = reply.get("conversation_id")
    if conv_id and conv_id in state["conversations"]:
        conv = state["conversations"][conv_id]
        mid = reply.get("conversation_message_id")
        msg = state["conversation_messages"].get(mid) if mid else None
        if msg:
            return conv, msg
    conv_id = state["next_conversation"]
    state["next_conversation"] += 1
    conv = {
        "id": conv_id, "confession_id": conf["id"], "user_a": conf["user_id"],
        "user_b": reply["from_user"], "status": "pending", "created": time.time(),
    }
    state["conversations"][conv_id] = conv
    mid = state["next_conversation_message"]
    state["next_conversation_message"] += 1
    msg = {
        "id": mid, "conversation_id": conv_id, "from_user": reply["from_user"],
        "to_user": conf["user_id"], "text": reply["text"], "html": reply.get("html"),
        "status": "pending", "created": reply.get("created", time.time()), "source": "initial_reply",
        "reply_id": reply["id"],
    }
    state["conversation_messages"][mid] = msg
    reply["conversation_id"] = conv_id
    reply["conversation_message_id"] = mid
    mark_dirty()
    return conv, msg


async def deliver_conversation_message(ctx: ContextTypes.DEFAULT_TYPE, conv: dict[str, Any],
                                       msg: dict[str, Any], recipient_id: int) -> bool:
    title = f"💌 <b>رد مجهول على T{conv['confession_id']}:</b>\n\n" if msg.get("source") == "initial_reply" else "💬 <b>رسالة مجهولة:</b>\n\n"
    markup = conversation_keyboard(conv["id"], msg["id"], include_reply=True)
    try:
        await ctx.bot.send_message(
            recipient_id, title + stored_html(msg), parse_mode=ParseMode.HTML,
            reply_markup=markup,
        )
        return True
    except Exception as e:
        log.warning("Could not deliver conversation message M%s to %s: %s", msg["id"], recipient_id, e)
        return False


async def approve_initial_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                                reply: dict[str, Any]) -> bool:
    conv, msg = create_conversation_for_reply(reply)
    recipient_id = msg["to_user"]
    # Don't finalize the reply until the actual first delivery succeeds.
    reply["status"] = "approving"
    msg["status"] = "approving"
    mark_dirty()
    delivered = await deliver_conversation_message(ctx, conv, msg, recipient_id)
    if not delivered:
        reply["status"] = "pending"
        msg["status"] = "pending"
        conv["status"] = "pending"
        mark_dirty()
        return False
    reply["status"] = "approved"
    msg["status"] = "approved"
    conv["status"] = "active"
    conv["last_activity"] = time.time()
    mark_dirty()
    sender_text = TXT_REPLY_DELIVERED_TO_SENDER.format(cid=reply["confession_id"])
    await safe_send(ctx, reply["from_user"], sender_text, reply_markup=conversation_keyboard(conv["id"], include_reply=True))
    return True


async def begin_conversation_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE, conv_id: int) -> None:
    conv = get_conversation(conv_id)
    uid = update.effective_user.id
    if not conv or conv.get("status") != "active" or conversation_other(conv, uid) is None:
        await update.effective_message.reply_text("المحادثة مش متاحة.")
        return
    suspended = suspension_error(uid)
    if suspended:
        await update.effective_message.reply_text(suspended)
        return
    ctx.user_data.pop("reply_to", None)
    ctx.user_data.pop("awaiting_number", None)
    ctx.user_data["conversation_reply_to"] = conv_id
    await update.effective_message.reply_text(f"✍️ ابعت رسالتك المجهولة في المحادثة C{conv_id} (أو /cancel).")


async def submit_conversation_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                                      conv_id: int, plain: str, formatted: str) -> None:
    """Deliver in-conversation messages immediately; only a report triggers review."""
    uid = update.effective_user.id
    conv = get_conversation(conv_id)
    recipient = conversation_other(conv, uid) if conv else None
    if not conv or conv.get("status") != "active" or recipient is None:
        await update.message.reply_text(TXT_CONV_CLOSED)
        return
    if not plain:
        await update.message.reply_text("ابعت نص الرسالة، أو /cancel للإلغاء.")
        return
    if len(plain) > MAX_LEN:
        await update.message.reply_text(TXT_TOO_LONG.format(max=MAX_LEN))
        return
    error = check_submission(uid, plain, "conversation")
    if error:
        await update.message.reply_text(error)
        return

    mid = state["next_conversation_message"]
    state["next_conversation_message"] += 1
    msg = {
        "id": mid, "conversation_id": conv_id, "from_user": uid, "to_user": recipient,
        "text": plain, "html": formatted, "status": "sending", "created": time.time(),
        "source": "conversation",
    }
    state["conversation_messages"][mid] = msg
    mark_dirty()

    # No pre-moderation: report controls are attached to the delivered message.
    delivered = await deliver_conversation_message(ctx, conv, msg, recipient)
    if not delivered:
        msg["status"] = "delivery_failed"
        mark_dirty()
        await update.message.reply_text(TXT_CONVERSATION_DELIVERY_FAILED)
        return

    msg["status"] = "approved"
    conv["last_activity"] = time.time()
    record_submission(uid, plain, "conversation")
    mark_dirty()
    await update.message.reply_text(
        TXT_CONVERSATION_DELIVERED,
        reply_markup=conversation_keyboard(conv_id, include_reply=True),
    )


async def conversation_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    uid = q.from_user.id
    if not q.message or q.message.chat.type != ChatType.PRIVATE:
        await q.answer("افتح البوت في الخاص عشان تستخدم المحادثة.", show_alert=True)
        return
    action, _, raw_id = q.data.partition(":")
    item_id = int(raw_id)
    await q.answer()
    if action == "convreply":
        await begin_conversation_reply(update, ctx, item_id)
    elif action == "convopen":
        await show_conversation(ctx, uid, item_id)
    elif action == "closeconv":
        conv = get_conversation(item_id)
        if not conv or conversation_other(conv, uid) is None:
            await ctx.bot.send_message(uid, "المحادثة مش موجودة.")
            return
        if conv.get("status") != "active":
            await ctx.bot.send_message(uid, "المحادثة مش مفتوحة.")
            return
        other_uid = conversation_other(conv, uid)
        conv["status"] = "closed"
        conv["closed_by"] = uid
        conv["closed_at"] = time.time()
        mark_dirty()
        await ctx.bot.send_message(uid, f"✅ أنهيت المحادثة C{item_id}. مش هتقدروا تبعتوا رسائل جديدة فيها.")
        if other_uid:
            await safe_send(ctx, other_uid, f"ℹ️ الطرف التاني أنهى المحادثة المجهولة C{item_id}. مش هتقدروا تبعتوا رسائل جديدة فيها.")


async def show_conversation(ctx: ContextTypes.DEFAULT_TYPE, uid: int, conv_id: int) -> None:
    conv = get_conversation(conv_id)
    if not conv or conversation_other(conv, uid) is None:
        await ctx.bot.send_message(uid, "المحادثة مش موجودة.")
        return
    messages = [m for m in state["conversation_messages"].values()
                if m.get("conversation_id") == conv_id
                and (m.get("from_user") == uid or m.get("status") == "approved")]
    messages.sort(key=lambda m: (m.get("created", 0), m["id"]))
    messages = messages[-8:]
    conv_status = ("مفتوحة" if conv.get("status") == "active" else
                   "مقفولة" if conv.get("status") == "closed" else "قيد التفعيل")
    lines = [f"💬 محادثة مجهولة C{conv_id} — اعتراف T{conv['confession_id']}",
             f"الحالة: {conv_status}", ""]
    for m in messages:
        who = "أنت" if m.get("from_user") == uid else "الطرف التاني"
        status = ""
        if m.get("from_user") == uid:
            if m.get("status") in ("pending", "approving"):
                status = " (تحت المراجعة)"
            elif m.get("status") == "rejected":
                status = " (لم تتم الموافقة)"
        body = m.get("text", "")
        if len(body) > 400:
            body = body[:400] + "… (تكملة الرسالة في إشعارها الأصلي)"
        lines.append(f"{who}{status}:\n{body}\n")
    rows = []
    if conv.get("status") == "active":
        rows.append([("↩️ رد مجهول", f"convreply:{conv_id}")])
        rows.append([("⏹️ إنهاء المحادثة", f"closeconv:{conv_id}")])
    rows.append([("🚩 إبلاغ عن المحادثة", f"reportconv:{conv_id}")])
    await ctx.bot.send_message(uid, "\n".join(lines), reply_markup=kb(rows))

# ---------------------------------------------------------------------------
# MyTalk dashboard
async def send_mytalk(bot, uid: int) -> None:
    confs = [c for c in state["confessions"].values()
             if c.get("user_id") == uid and c.get("status") in ("pending", "approved")]
    confs.sort(key=lambda c: c.get("created", 0), reverse=True)
    convs = [c for c in state["conversations"].values()
             if uid in (c.get("user_a"), c.get("user_b")) and c.get("status") in ("active", "pending", "closed")]
    convs.sort(key=lambda c: c.get("last_activity", c.get("created", 0)), reverse=True)
    lines = ["💌 MyTalk", "كل اللي ظاهر هنا خاص بيك.", "", "📝 اعترافاتك:"]
    if not confs:
        lines.append("— مفيش اعترافات قيد المراجعة أو منشورة لسه.")
    else:
        for conf in confs[:10]:
            status = "🕓 قيد المراجعة" if conf.get("status") == "pending" else "✅ منشور"
            preview = " ".join(conf.get("text", "").split())
            if len(preview) > 90:
                preview = preview[:90] + "…"
            lines.append(f"T{conf['id']} · {status}\n{preview}")
    lines.extend(["", "💬 محادثاتك المجهولة:"])
    if not convs:
        lines.append("— مفيش محادثات بدأت لسه.")
    else:
        for conv in convs[:10]:
            status = ("مفتوحة" if conv.get("status") == "active" else
                      "قيد التفعيل" if conv.get("status") == "pending" else "مقفولة")
            latest = next((m for m in sorted(state["conversation_messages"].values(), key=lambda x: x.get("created", 0), reverse=True)
                           if m.get("conversation_id") == conv["id"] and (m.get("from_user") == uid or m.get("status") == "approved")), None)
            preview = ""
            if latest:
                preview = " ".join(latest.get("text", "").split())[:65]
                if len(latest.get("text", "")) > 65:
                    preview += "…"
            lines.append(f"C{conv['id']} · T{conv['confession_id']} · {status}" + (f"\n{preview}" if preview else ""))
    buttons = [[(f"💬 C{c['id']} — T{c['confession_id']}", f"convopen:{c['id']}")] for c in convs[:10]]
    buttons.append([("🔒 إعدادات الخصوصية", "settings:open")])
    await bot.send_message(uid, "\n".join(lines), reply_markup=kb(buttons))

# ---------------------------------------------------------------------------
# Reporting and moderation tools
def build_report_transcript(conv: dict[str, Any], report: dict[str, Any]) -> str:
    """Create a plain-text audit log for admins; expose participant IDs only in this report."""
    conv_id = int(conv["id"])
    uid_a, uid_b = int(conv["user_a"]), int(conv["user_b"])
    confession = state["confessions"].get(int(conv.get("confession_id", 0)), {})
    created = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(float(report.get("created", time.time()))))
    lines = [
        "TIO — REPORTED ANONYMOUS CONVERSATION LOG",
        "=" * 52,
        f"Report ID: RPT{report['id']}",
        f"Report created: {created}",
        f"Report type: {report.get('target_type')}",
        f"Reported target ID: {report.get('target_id')}",
        f"Conversation ID: C{conv_id}",
        f"Related confession ID: T{conv.get('confession_id')}",
        f"Participant A Telegram user ID: {uid_a}",
        f"Participant B Telegram user ID: {uid_b}",
        f"Reporter Telegram user ID: {report.get('reporter_id')}",
        f"Reported participant Telegram user ID: {report.get('reported_user_id')}",
        f"Conversation status: {conv.get('status', 'unknown')}",
        "",
        "RELATED CONFESSION (context)",
        "-" * 52,
        confession.get("text", "[Confession text unavailable]"),
        "",
        "FULL CONVERSATION TRANSCRIPT",
        "-" * 52,
    ]
    messages = [m for m in state["conversation_messages"].values()
                if int(m.get("conversation_id", -1)) == conv_id]
    messages.sort(key=lambda m: (float(m.get("created", 0)), int(m.get("id", 0))))
    if not messages:
        lines.append("[No conversation messages found]")
    for msg in messages:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(float(msg.get("created", 0))))
        lines.extend([
            f"Message M{msg.get('id')} | {stamp}",
            f"From Telegram user ID: {msg.get('from_user')}",
            f"To Telegram user ID: {msg.get('to_user')}",
            f"Status: {msg.get('status', 'unknown')} | Source: {msg.get('source', 'unknown')}",
            "Message text:",
            msg.get("text", ""),
            "",
        ])
    lines.append("END OF LOG — Handle this report and its identifiers confidentially.")
    return "\n".join(lines)


async def send_report_log(ctx: ContextTypes.DEFAULT_TYPE, conv: dict[str, Any], report: dict[str, Any]) -> None:
    transcript = build_report_transcript(conv, report)
    filename = f"tio_report_RPT{report['id']}_C{conv['id']}.txt"
    buf = io.BytesIO(transcript.encode("utf-8"))
    buf.name = filename
    try:
        await ctx.bot.send_document(
            ADMIN_GROUP_ID,
            document=InputFile(buf, filename=filename),
            caption=(f"📄 سجل المحادثة الكامل للبلاغ RPT{report['id']} — C{conv['id']}\n"
                     f"Participant A UID: {conv['user_a']} | Participant B UID: {conv['user_b']}"),
            disable_notification=False,
        )
    except TelegramError:
        log.exception("Could not upload transcript for report RPT%s", report["id"])
        # A fallback makes the transcript reviewable even if document upload fails.
        await safe_admin_notice(ctx.bot, f"⚠️ تعذر رفع ملف RPT{report['id']}؛ هيتبعت السجل كنص مقسّم.")
        for offset in range(0, len(transcript), 3500):
            try:
                await ctx.bot.send_message(ADMIN_GROUP_ID, transcript[offset:offset + 3500])
            except TelegramError:
                log.exception("Could not send transcript text fallback for RPT%s", report["id"])
                break


async def create_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE, target_type: str, target_id: int) -> None:
    uid = update.effective_user.id
    if target_type == "message":
        item = state["conversation_messages"].get(target_id)
        if not item or item.get("status") not in ("approved", "delivery_failed"):
            await update.effective_message.reply_text("الرسالة دي مش متاحة للبلاغ.")
            return
        conv = get_conversation(item["conversation_id"])
        if not conv or conversation_other(conv, uid) is None or item.get("from_user") == uid:
            await update.effective_message.reply_text("مينفعش تبلغ عن رسالتك إنت.")
            return
        reported_user_id = item["from_user"]
        conversation_id = int(conv["id"])
    else:
        conv = get_conversation(target_id)
        if not conv or conversation_other(conv, uid) is None:
            await update.effective_message.reply_text("المحادثة مش متاحة للبلاغ.")
            return
        reported_user_id = conversation_other(conv, uid)
        conversation_id = int(conv["id"])

    existing = next((r for r in state["reports"].values()
                     if r.get("reporter_id") == uid and r.get("target_type") == target_type
                     and r.get("target_id") == target_id and r.get("status") == "pending"), None)
    if existing:
        await update.effective_message.reply_text(TXT_REPORT_DUPLICATE)
        return

    rid = state["next_report"]
    state["next_report"] += 1
    report = {
        "id": rid, "reporter_id": uid, "target_type": target_type, "target_id": target_id,
        "conversation_id": conversation_id, "reported_user_id": reported_user_id,
        "status": "pending", "created": time.time(),
    }
    state["reports"][rid] = report
    mark_dirty()

    if target_type == "message":
        item = state["conversation_messages"][target_id]
        detail = (f"<b>بلاغ عن الرسالة M{target_id} في المحادثة C{conversation_id}</b>\n"
                  f"نص الرسالة: {esc(item.get('text', '')[:1000])}")
    else:
        detail = f"<b>بلاغ عن المحادثة C{conversation_id}</b>\nاعتراف مرتبط: T{conv['confession_id']}"
    admin_text = (
        f"🚩 <b>بلاغ جديد RPT{rid}</b>\n"
        f"<i>النوع: {esc(target_type)} • المبلّغ UID <code>{uid}</code> • "
        f"الطرف المبلّغ عنه UID <code>{reported_user_id}</code></i>\n"
        f"<i>Participant A UID <code>{conv['user_a']}</code> • "
        f"Participant B UID <code>{conv['user_b']}</code></i>\n\n{detail}\n\n"
        "📄 سجل المحادثة الكامل مرفق كملف TXT."
    )
    try:
        await ctx.bot.send_message(
            ADMIN_GROUP_ID, admin_text, parse_mode=ParseMode.HTML,
            reply_markup=kb([[('✅ إغلاق البلاغ', f'rclose:{rid}')],
                             [('⛔ إيقاف ساعة', f'sus:{rid}:3600'), ('⛔ إيقاف 24 ساعة', f'sus:{rid}:86400')]]),
        )
    except TelegramError:
        log.exception("Could not send report RPT%s to moderators", rid)
    await send_report_log(ctx, conv, report)
    await update.effective_message.reply_text(TXT_REPORT_SENT)


async def is_admin_user(bot, uid: int) -> bool:
    if ADMIN_IDS:
        return uid in ADMIN_IDS
    try:
        member = await bot.get_chat_member(ADMIN_GROUP_ID, uid)
        return member.status in ("administrator", "creator")
    except TelegramError:
        return False


async def suspend_user(bot, uid: int, seconds: int, reason: str = "moderation") -> None:
    u = state["users"].setdefault(uid, {"user_id": uid, "identity_mode": "anonymous", "submission_events": []})
    u["suspended_until"] = max(float(u.get("suspended_until") or 0), time.time() + seconds)
    u["suspend_reason"] = reason[:200]
    mark_dirty()
    await safe_admin_notice(bot, f"⛔ تم إيقاف UID <code>{uid}</code> لمدة {max(1, seconds // 60)} دقيقة.")


async def safe_admin_notice(bot, text: str) -> None:
    try:
        await bot.send_message(ADMIN_GROUP_ID, text, parse_mode=ParseMode.HTML)
    except TelegramError:
        log.exception("Could not send admin notice")


async def admin_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q.message or q.message.chat.id != ADMIN_GROUP_ID or not await is_admin_user(ctx.bot, q.from_user.id):
        await q.answer(TXT_NOT_ADMIN_GROUP, show_alert=True)
        return
    action, _, raw = q.data.partition(":")
    admin_name = esc(q.from_user.first_name or "Admin")

    if action in ("ac", "rc"):
        cid = int(raw)
        row = state["confessions"].get(cid)
        if not row or row.get("status") != "pending":
            await q.answer(TXT_ALREADY_HANDLED, show_alert=True)
            return
        if action == "rc":
            row["status"] = "rejected"
            mark_dirty()
            await safe_send(ctx, row["user_id"], TXT_CONF_REJECTED.format(cid=cid) if TXT_CONF_REJECTED else None)
            verdict = TXT_VERDICT_REJECTED
        else:
            # Mark as publishing during the network call; only mark approved after success.
            row["status"] = "publishing"
            mark_dirty()
            owner = get_user(row["user_id"])
            post = TXT_CHANNEL_POST.format(cid=cid, label=esc(label(owner)), text=stored_html(row))
            if owner and owner.get("allow_replies"):
                post += TXT_CHANNEL_REPLY_HINT.format(cid=cid)
            post += TXT_CHANNEL_FOOTER
            try:
                posted = await ctx.bot.send_message(CHANNEL_ID, post, parse_mode=ParseMode.HTML)
            except TelegramError as e:
                log.error("Channel post T%s failed: %s", cid, e)
                row["status"] = "pending"
                row["last_publish_error"] = str(e)[:300]
                mark_dirty()
                await q.answer("النشر فشل؛ الاعتراف لسه Pending وتقدر تجرب تاني.", show_alert=True)
                await q.message.reply_text(TXT_CHANNEL_FAIL_WARNING.format(cid=cid))
                return
            row["status"] = "approved"
            row["channel_message_id"] = posted.message_id
            row["published_at"] = time.time()
            mark_dirty()
            await safe_send(ctx, row["user_id"], TXT_CONF_APPROVED_PUBLISHED.format(cid=cid))
            verdict = TXT_VERDICT_APPROVED
        await q.edit_message_text(
            f"{q.message.text_html or esc(q.message.text or '')}\n\n" +
            TXT_VERDICT_LINE.format(verdict=verdict, admin=admin_name), parse_mode=ParseMode.HTML,
        )
        await q.answer(TXT_OK_TOAST)
        return

    if action in ("ar", "rr"):
        rid = int(raw)
        row = state["replies"].get(rid)
        if not row or row.get("status") != "pending":
            await q.answer(TXT_ALREADY_HANDLED, show_alert=True)
            return
        if action == "rr":
            row["status"] = "rejected"
            mark_dirty()
            await safe_send(ctx, row["from_user"], TXT_REPLY_REJECTED_TO_SENDER.format(cid=row["confession_id"]) if TXT_REPLY_REJECTED_TO_SENDER else None)
            verdict = TXT_VERDICT_REJECTED
        else:
            succeeded = await approve_initial_reply(update, ctx, row)
            if not succeeded:
                await q.answer("التسليم فشل؛ الرد لسه Pending وجرب الموافقة تاني بعد حل المشكلة.", show_alert=True)
                return
            verdict = TXT_VERDICT_APPROVED
        await q.edit_message_text(
            f"{q.message.text_html or esc(q.message.text or '')}\n\n" +
            TXT_VERDICT_LINE.format(verdict=verdict, admin=admin_name), parse_mode=ParseMode.HTML,
        )
        await q.answer(TXT_OK_TOAST)
        return

    if action in ("cm", "xm"):
        mid = int(raw)
        msg = state["conversation_messages"].get(mid)
        if not msg or msg.get("status") != "pending":
            await q.answer(TXT_ALREADY_HANDLED, show_alert=True)
            return
        conv = get_conversation(msg["conversation_id"])
        if action == "xm":
            msg["status"] = "rejected"
            mark_dirty()
            verdict = TXT_VERDICT_REJECTED
        else:
            msg["status"] = "approving"
            mark_dirty()
            recipient = msg["to_user"]
            delivered = await deliver_conversation_message(ctx, conv, msg, recipient)
            if not delivered:
                msg["status"] = "pending"
                mark_dirty()
                await q.answer("التسليم فشل؛ الرسالة لسه Pending وتقدر تجرب تاني.", show_alert=True)
                return
            msg["status"] = "approved"
            conv["last_activity"] = time.time()
            mark_dirty()
            await safe_send(ctx, msg["from_user"], f"✅ رسالتك اتسلمت للطرف التاني في C{conv['id']}.",
                            reply_markup=conversation_keyboard(conv["id"], include_reply=True))
            verdict = TXT_VERDICT_APPROVED
        await q.edit_message_text(
            f"{q.message.text_html or esc(q.message.text or '')}\n\n" +
            TXT_VERDICT_LINE.format(verdict=verdict, admin=admin_name), parse_mode=ParseMode.HTML,
        )
        await q.answer(TXT_OK_TOAST)
        return

    if action == "rclose":
        rid = int(raw)
        report = state["reports"].get(rid)
        if not report or report.get("status") != "pending":
            await q.answer(TXT_ALREADY_HANDLED, show_alert=True)
            return
        report["status"] = "reviewed"
        report["reviewed_by"] = q.from_user.id
        report["reviewed_at"] = time.time()
        mark_dirty()
        await q.edit_message_text(f"{q.message.text_html or esc(q.message.text or '')}\n\n✅ تم إغلاق البلاغ بواسطة {admin_name}", parse_mode=ParseMode.HTML)
        await q.answer(TXT_OK_TOAST)
        return

    if action == "sus":
        parts = raw.split(":")
        if len(parts) != 2:
            await q.answer("طلب غير صالح", show_alert=True)
            return
        rid, seconds = int(parts[0]), int(parts[1])
        report = state["reports"].get(rid)
        if not report or report.get("status") != "pending":
            await q.answer(TXT_ALREADY_HANDLED, show_alert=True)
            return
        target_uid = report.get("reported_user_id")
        if not target_uid:
            await q.answer("مش قادر أحدد الحساب المستهدف.", show_alert=True)
            return
        user = state["users"].setdefault(target_uid, {"user_id": target_uid, "identity_mode": "anonymous", "submission_events": []})
        user["suspended_until"] = max(float(user.get("suspended_until") or 0), time.time() + seconds)
        user["suspend_reason"] = f"report {rid}"
        report["status"] = "actioned"
        report["reviewed_by"] = q.from_user.id
        report["reviewed_at"] = time.time()
        mark_dirty()
        await q.edit_message_text(f"{q.message.text_html or esc(q.message.text or '')}\n\n⛔ تم إيقاف UID <code>{target_uid}</code> لمدة {seconds // 3600 or 1} ساعة بواسطة {admin_name}", parse_mode=ParseMode.HTML)
        await q.answer(TXT_OK_TOAST)
        return

# ---------------------------------------------------------------------------
# Commands for admins
async def suspend_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != ADMIN_GROUP_ID or not await is_admin_user(ctx.bot, update.effective_user.id):
        await update.message.reply_text(TXT_NOT_ADMIN_GROUP)
        return
    if len(ctx.args) < 2:
        await update.message.reply_text("الاستخدام: /suspend USER_ID MINUTES [reason]")
        return
    try:
        uid, minutes = int(ctx.args[0]), int(ctx.args[1])
        if minutes < 1 or minutes > 525600:
            raise ValueError
    except ValueError:
        await update.message.reply_text("ابعت رقم مستخدم صحيح ومدة بالدقائق من 1 إلى 525600.")
        return
    reason = " ".join(ctx.args[2:]) or "admin suspension"
    u = state["users"].setdefault(uid, {"user_id": uid, "identity_mode": "anonymous", "submission_events": []})
    u["suspended_until"] = max(float(u.get("suspended_until") or 0), time.time() + minutes * 60)
    u["suspend_reason"] = reason[:200]
    mark_dirty()
    await update.message.reply_text(f"⛔ تم إيقاف UID {uid} لمدة {minutes} دقيقة.")


async def unsuspend_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.id != ADMIN_GROUP_ID or not await is_admin_user(ctx.bot, update.effective_user.id):
        await update.message.reply_text(TXT_NOT_ADMIN_GROUP)
        return
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("الاستخدام: /unsuspend USER_ID")
        return
    uid = int(ctx.args[0])
    u = get_user(uid)
    if not u:
        await update.message.reply_text("المستخدم مش موجود في قاعدة البيانات.")
        return
    u["suspended_until"] = 0
    u["suspend_reason"] = ""
    mark_dirty()
    await update.message.reply_text(f"✅ تم إلغاء إيقاف UID {uid}.")

async def ban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: /ban USER_ID HOURS."""
    if update.effective_chat.id != ADMIN_GROUP_ID or not await is_admin_user(ctx.bot, update.effective_user.id):
        await update.message.reply_text(TXT_NOT_ADMIN_GROUP)
        return
    if len(ctx.args) != 2:
        await update.message.reply_text("الاستخدام: /ban USER_ID HOURS\nمثال: /ban 123456789 24")
        return
    try:
        uid = int(ctx.args[0])
        hours = int(ctx.args[1])
        if uid <= 0 or not 1 <= hours <= 8760:
            raise ValueError
    except ValueError:
        await update.message.reply_text("استخدم ID صحيح وعدد ساعات من 1 إلى 8760 (سنة كحد أقصى).")
        return
    u = state["users"].setdefault(uid, {
        "user_id": uid, "identity_mode": "anonymous", "submission_events": [],
        "suspended_until": 0, "suspend_reason": "",
    })
    until = time.time() + hours * 3600
    u["suspended_until"] = max(float(u.get("suspended_until") or 0), until)
    u["suspend_reason"] = f"admin ban for {hours} hours"
    mark_dirty()
    until_text = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(u["suspended_until"]))
    await update.message.reply_text(f"⛔ تم حظر UID {uid} لمدة {hours} ساعة. ينتهي في {until_text}.")


async def unban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: /unban USER_ID."""
    if update.effective_chat.id != ADMIN_GROUP_ID or not await is_admin_user(ctx.bot, update.effective_user.id):
        await update.message.reply_text(TXT_NOT_ADMIN_GROUP)
        return
    if len(ctx.args) != 1:
        await update.message.reply_text("الاستخدام: /unban USER_ID\nمثال: /unban 123456789")
        return
    try:
        uid = int(ctx.args[0])
        if uid <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("ابعت Telegram user ID صحيح.")
        return
    u = get_user(uid)
    if not u:
        await update.message.reply_text("المستخدم مش موجود في قاعدة البيانات.")
        return
    u["suspended_until"] = 0
    u["suspend_reason"] = ""
    mark_dirty()
    await update.message.reply_text(f"✅ تم إلغاء الحظر عن UID {uid}.")


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ("reply_to", "awaiting_number", "conversation_reply_to", "compose_confession"):
        ctx.user_data.pop(key, None)
    await update.message.reply_text(TXT_CANCELLED, reply_markup=home_markup() if update.effective_chat.type == ChatType.PRIVATE else None)


async def mytalk_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    if not profile_complete(get_user(update.effective_user.id)):
        await update.message.reply_text(TXT_NEED_START)
        return
    await send_mytalk(ctx.bot, update.effective_user.id)


async def settings_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    if not get_user(update.effective_user.id):
        await update.message.reply_text(TXT_NEED_START)
        return
    await send_settings(ctx.bot, update.effective_user.id)


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type == ChatType.PRIVATE:
        await update.message.reply_text(TXT_HELP, parse_mode=ParseMode.MARKDOWN, reply_markup=home_markup())


async def chat_id_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"ID الشات: {update.effective_chat.id}")

# ---------------------------------------------------------------------------
# Private incoming text router
async def private_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return
    uid = msg.from_user.id
    u = get_user(uid)
    plain = msg.text.strip()

    # Persistent home-keyboard actions.
    if plain == HOME_WRITE:
        if not profile_complete(u):
            await msg.reply_text(TXT_NEED_START)
            return
        ctx.user_data["compose_confession"] = True
        ctx.user_data.pop("reply_to", None)
        ctx.user_data.pop("conversation_reply_to", None)
        await msg.reply_text("✍️ اكتب اعترافك دلوقتي. تقدر تلغيه بـ /cancel.")
        return
    if plain == HOME_MYTALK:
        if not profile_complete(u):
            await msg.reply_text(TXT_NEED_START)
            return
        await send_mytalk(ctx.bot, uid)
        return
    if plain == HOME_PRIVACY:
        await send_settings(ctx.bot, uid)
        return
    if plain == HOME_HELP:
        await msg.reply_text(TXT_HELP, parse_mode=ParseMode.MARKDOWN, reply_markup=home_markup())
        return

    if not profile_complete(u):
        await msg.reply_text(TXT_NEED_START)
        return
    touch_user(msg.from_user)
    formatted = msg.text_html.strip()

    if ctx.user_data.get("awaiting_number"):
        m = NUMBER_RE.match(plain)
        if not m:
            await msg.reply_text(TXT_BAD_NUMBER)
            return
        ctx.user_data.pop("awaiting_number", None)
        await begin_reply(update, ctx, int(m.group(1)))
        return

    conv_pending = ctx.user_data.pop("conversation_reply_to", None)
    if conv_pending:
        await submit_conversation_message(update, ctx, int(conv_pending), plain, formatted)
        return

    # Quick syntax: T5 Reply text
    m = REPLY_RE.match(plain)
    if m and not ctx.user_data.get("compose_confession"):
        cid, body_plain = int(m.group(1)), m.group(2).strip()
        if not body_plain:
            await begin_reply(update, ctx, cid)
            return
        formatted_match = REPLY_RE.match(formatted)
        body_html = formatted_match.group(2).strip() if formatted_match else esc(body_plain)
        await submit_reply(update, cid, body_plain, body_html)
        return

    if ctx.user_data.get("reply_to"):
        cid = int(ctx.user_data.pop("reply_to"))
        await submit_reply(update, cid, plain, formatted)
        return

    ctx.user_data.pop("compose_confession", None)
    await submit_confession(update, ctx, u, plain, formatted)

# ---------------------------------------------------------------------------
# Main

def main() -> None:
    app = (Application.builder().token(BOT_TOKEN).post_init(on_start).post_stop(on_stop).build())
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_cmd))
    app.add_handler(CommandHandler("mytalk", mytalk_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("chatid", chat_id_cmd))
    app.add_handler(CommandHandler("suspend", suspend_cmd))
    app.add_handler(CommandHandler("unsuspend", unsuspend_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CallbackQueryHandler(onboarding_cb, pattern=r"^(im|g|c|grp|pr):"))
    app.add_handler(CallbackQueryHandler(settings_cb, pattern=r"^(privacy|replies|settings):"))
    app.add_handler(CallbackQueryHandler(conversation_cb, pattern=r"^(convreply|convopen|closeconv):"))
    app.add_handler(CallbackQueryHandler(user_report_cb, pattern=r"^(reportmsg|reportconv):"))
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^(ac|rc|ar|rr|cm|xm|rclose|sus):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, private_text))
    log.info("Tio is running…")
    app.run_polling()


if __name__ == "__main__":
    main()
