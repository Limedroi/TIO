"""
Tio - Talk It Out!  (بوت الاعترافات)

Install:  pip install "python-telegram-bot>=20.7" python-dotenv
Run:      BOT_TOKEN=123:ABC python tio_bot.py

Storage
 - Data (users, confessions, replies) lives in memory and is saved as
   tio_data.json inside a .zip in the BACKUP group.
 - Debounce: the first unsaved change starts a timer (BACKUP_DELAY, default
   60s). When it ends, ONE backup containing every change made meanwhile is
   sent and pinned (previous backup message is deleted).
 - On startup the bot downloads the pinned zip and restores everything.
 - The bot must be ADMIN in the backup group with Pin + Delete permissions.
"""

# =====================================================================
#                       ✏️  UI  —  EDIT FREELY  ✏️
# =====================================================================
# Notes:
#  * {curly_names} are filled in by the bot - keep them exactly as written.
#  * Texts marked [MD] use Telegram Markdown:  *bold*  `code`
#  * Texts marked [HTML] use HTML:  <b>bold</b>  <i>italic</i>  <code>code</code>
#    (user-written content is escaped automatically)
#  * Texts marked [plain] have no formatting.

# ---------- Onboarding buttons: (button text, stored value) ----------
GENDER_OPTIONS = [("👨 ولد", "ولد"), ("👩 بنت", "بنت")]
CLASS_OPTIONS = [("دفعة 44", "44"), ("دفعة 45", "45")]
GROUPS = [f"G{i}" for i in range(1, 10)]          # G1 ... G9
BTN_HIDDEN_GROUP = "🤐 مفضلش أقول"
BTN_ALLOW_REPLIES = "✅ اسمح"
BTN_DENY_REPLIES = "🚫 متسمحش"

# ---------- Admin buttons ----------
BTN_APPROVE = "✅ موافقة"
BTN_REJECT = "❌ رفض"

# ---------- Onboarding messages ----------
TXT_WELCOME = (                                    # [MD]
    "أهلاً بيك في *Tio — Talk It Out!* 👋\n"
    "فضفض وأتكلم براحتك زي ما تحب\n\n"
    "الأول، إنت:"
)
TXT_ASK_CLASS = "إنت في أنهي دفعة؟"                # [plain]
TXT_ASK_GROUP = "إنت في أنهي جروب؟"                # [plain]
TXT_ASK_REPLIES = (                                # [MD]
    "تحب تسمح بـ *الردود الخاصة*؟\n"
    "أي حد يقدر يرد على رسالتك بأستخدام `/reply 12`"
)
TXT_SETUP_DONE = (                                 # [MD]
    "🎉 كده تمام!\n\n"
    "✍️ ابعتلي رسالتك في رسالة عادية .\n"
    "💬 عشان ترد على حد: اكتب /reply أو ابعت `T5 ردك`.\n"
    "🔁 اكتب /start لو عايز تعيد."
)

# ---------- User messages ----------
TXT_NEED_START = "اضغط /start الأول عشان تظبط بياناتك."                       # [plain]
TXT_CONFESSION_RECEIVED = "✅ اعترافك اتسجل برقم *T{cid}* وبيستنى الموافقة."    # [MD]
TXT_ASK_REPLY_TEXT = "✍️ ابعت ردك على T{cid} دلوقتي (أو /cancel)."             # [plain]
TXT_CONFESSION_NOT_FOUND = "❌ الاعتراف T{cid} مش موجود."                       # [plain]
TXT_REPLIES_DISABLED = "🚫 صاحب T{cid} مش مسمّح بالردود الخاصة."                # [plain]
TXT_OWN_CONFESSION = "مينفعش ترد على اعترافك إنت 🙂"                            # [plain]
TXT_REPLY_SENT_FOR_REVIEW = "✅ الرد اتبعت لـ T{cid}"                            # [plain]
TXT_CANCELLED = "اتلغى."                                                        # [plain]
TXT_ASK_REPLY_NUMBER = "🔢 ابعت رقم الاعتراف اللي عايز ترد عليه (مثلاً T5 أو 5)."  # [plain]
TXT_BAD_NUMBER = "❌ الرقم مش مظبوط. ابعت رقم الاعتراف (مثلاً T5 أو 5) أو /cancel."  # [plain]
TXT_TOO_LONG = "❌ الرسالة طويلة قوي. الحد الأقصى {max} حرف."                      # [plain]
MAX_LEN = 3000   # max characters for a confession / reply

# ---------- Command menu (the "/" button in Telegram) ----------
COMMANDS = [
    ("start", "ابدأ أو غيّر بياناتك"),
    ("reply", "رد على اعتراف"),
    ("cancel", "إلغاء"),
]

# ---------- Notifications to users after admin decision ----------
TXT_CONF_APPROVED_PUBLISHED = "✅ اعترافك T{cid} اتوافق عليه واتنشر."            # [plain]
TXT_CONF_APPROVED = "✅ اعترافك T{cid} اتوافق عليه."                             # [plain]
TXT_CONF_REJECTED = None   # None = silent (nothing is sent). Or put a text.
TXT_REPLY_DELIVERED_TO_OWNER = (                                                # [HTML]
    "💌 <b>رد مجهول على اعترافك T{cid}:</b>\n\n{text}"
)
TXT_REPLY_DELIVERED_TO_SENDER = None   # None = silent (nothing is sent). Or put a text.
TXT_REPLY_REJECTED_TO_SENDER = None   # None = silent (nothing is sent). Or put a text.

# ---------- Admin group messages ----------
TXT_ADMIN_NEW_CONFESSION = (                                                    # [HTML]
    "📩 <b>اعتراف جديد T{cid}</b>\n"
    "<i>{label} • الردود {replies}</i>\n\n{text}"
)
TXT_REPLIES_ON = "شغالة"
TXT_REPLIES_OFF = "مقفولة"
TXT_ADMIN_NEW_REPLY = (                                                         # [HTML]
    "💬 <b>رد R{rid} ← T{cid}</b>\n"
    "<i>من: {label}</i>\n\n"
    "<b>الاعتراف الأصلي:</b> {original}\n\n"
    "<b>الرد:</b> {text}"
)
TXT_VERDICT_APPROVED = "✅ تمت الموافقة"
TXT_VERDICT_REJECTED = "❌ اترفض"
TXT_VERDICT_LINE = "<b>{verdict}</b> بواسطة {admin}"                            # [HTML]
TXT_NOT_ADMIN_GROUP = "مش مسموحلك."                                             # popup
TXT_ALREADY_HANDLED = "اتعالج قبل كده."                                         # popup
TXT_OK_TOAST = "تمام"
TXT_CHANNEL_FAIL_WARNING = (                                                    # [plain]
    "⚠️ معرفتش أنشر T{cid} في القناة. اتأكد إن البوت أدمن هناك."
)

# ---------- Channel post ----------
TXT_CHANNEL_POST = "<b>T{cid}</b>\n<i>{label}</i>\n\n{text}"                    # [HTML]
# Only added when the author allows private replies:
TXT_CHANNEL_REPLY_HINT = (                                                      # [HTML]
    "\n\nلو عايز ترد عليه خاص ومخفي الهوية أستخدم /reply <code>T{cid}</code>"
)
# Always added at the end of every channel post (each line = its own quote block):
TXT_CHANNEL_FOOTER = (                                                          # [HTML]
    "\n\n<blockquote>البوت: @TIO44_bot</blockquote>"
    "\n<blockquote>القناة: https://t.me/TalkItOut_Channel</blockquote>"
)

# ---------- Profile label shown next to confessions ----------
LABEL_FORMAT = "{gender} • دفعة {cls} • {grp}"
LABEL_HIDDEN_GROUP = "الجروب مخفي"

# ---------- Misc ----------
TXT_CHAT_ID = "ID الشات: {id}"
TXT_BACKUP_CAPTION = (                                                          # [plain]
    "🗂 نسخة احتياطية\n"
    "👥 مستخدمين: {users}\n"
    "📩 اعترافات: {confessions}\n"
    "💬 ردود: {replies}"
)

# =====================================================================
#                         END OF UI SECTION
# =====================================================================

import asyncio
import io
import json
import logging
import os
import re
import time
import zipfile

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.constants import ParseMode
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ------------------------------------------------------------------ CONFIG
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is not set. Put it in the environment or a .env file.")

ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-5370857010"))
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1004439548910"))
BACKUP_GROUP_ID = int(os.environ.get("BACKUP_GROUP_ID", "-5044416482"))
BACKUP_DELAY = int(os.environ.get("BACKUP_DELAY", "60"))  # seconds

REPLY_RE = re.compile(r"^\s*[Tt](\d+)\s*(.*)$", re.DOTALL)
NUMBER_RE = re.compile(r"^\s*[Tt]?\s*(\d+)\s*$")
BACKUP_JSON_NAME = "tio_data.json"

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("tio")

# ------------------------------------------------------------------- STATE
state = {
    "users": {},          # user_id -> profile
    "confessions": {},    # id -> confession
    "replies": {},        # id -> reply
    "next_confession": 1,
    "next_reply": 1,
}
# dirty_since: monotonic time of the FIRST change not yet backed up (None = clean)
meta = {"dirty_since": None, "last_backup_msg": None, "lock": None}


def mark_dirty():
    """Record that something changed. Starts the debounce window if not running."""
    if meta["dirty_since"] is None:
        meta["dirty_since"] = time.monotonic()


def load_state(raw: bytes):
    s = json.loads(raw)
    for k in ("users", "confessions", "replies"):
        state[k] = {int(i): v for i, v in s.get(k, {}).items()}
    state["next_confession"] = s.get("next_confession", 1)
    state["next_reply"] = s.get("next_reply", 1)


# ------------------------------------------------------------------ BACKUP
async def flush_backup(bot):
    """Send + pin one backup. Serialized by a lock so two never overlap."""
    async with meta["lock"]:
        if meta["dirty_since"] is None:
            return
        # Snapshot first (no awaits in between), then mark clean: any change
        # that happens while uploading re-opens a new debounce window.
        payload = json.dumps(state, ensure_ascii=False, indent=1).encode("utf-8")
        counts = dict(users=len(state["users"]),
                      confessions=len(state["confessions"]),
                      replies=len(state["replies"]))
        meta["dirty_since"] = None

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(BACKUP_JSON_NAME, payload)
        buf.seek(0)
        name = f"tio_backup_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.zip"

        try:
            msg = await bot.send_document(
                BACKUP_GROUP_ID,
                document=InputFile(buf, filename=name),
                caption=TXT_BACKUP_CAPTION.format(**counts),
                disable_notification=True,
            )
            await bot.pin_chat_message(
                BACKUP_GROUP_ID, msg.message_id, disable_notification=True
            )
        except RetryAfter as e:
            # Telegram asked us to slow down: retry after the requested wait.
            meta["dirty_since"] = time.monotonic() - BACKUP_DELAY + e.retry_after + 1
            raise
        except Exception:
            # Failed: keep the data marked dirty and retry after a full window.
            meta["dirty_since"] = time.monotonic()
            raise

        old = meta["last_backup_msg"]
        meta["last_backup_msg"] = msg.message_id
        if old and old != msg.message_id:
            try:
                await bot.delete_message(BACKUP_GROUP_ID, old)
            except TelegramError as e:
                log.warning("Couldn't delete old backup: %s", e)


async def backup_loop(bot):
    """Checks every second; backs up once BACKUP_DELAY passed since the first change."""
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


async def restore_from_pinned(bot):
    """Load the pinned backup zip. Aborts startup if a backup exists but is
    unreadable, so an empty state can never overwrite real data."""
    chat = await bot.get_chat(BACKUP_GROUP_ID)
    pm = chat.pinned_message
    if not pm or not pm.document or not (pm.document.file_name or "").endswith(".zip"):
        log.info("No pinned backup found - starting fresh.")
        return
    f = await pm.document.get_file()
    data = bytes(await f.download_as_bytearray())
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        load_state(z.read(BACKUP_JSON_NAME))
    meta["last_backup_msg"] = pm.message_id
    log.info(
        "Restored backup: %d users, %d confessions, %d replies",
        len(state["users"]), len(state["confessions"]), len(state["replies"]),
    )


async def on_start(app: Application):
    meta["lock"] = asyncio.Lock()
    await restore_from_pinned(app.bot)
    try:
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])
    except TelegramError as e:
        log.warning("Couldn't set commands: %s", e)
    app.bot_data["backup_task"] = asyncio.create_task(backup_loop(app.bot))


async def on_stop(app: Application):
    """Flush pending changes immediately on graceful shutdown."""
    task = app.bot_data.get("backup_task")
    if task:
        task.cancel()
    if meta["dirty_since"] is not None:
        try:
            await flush_backup(app.bot)
        except Exception as e:
            log.error("Final backup failed: %s", e)


# ----------------------------------------------------------------- HELPERS
def fmt(template, **kw):
    """Fill a UI template; returns None when the template is None (= silent)."""
    return template.format(**kw) if template else None


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stored_html(item):
    """Formatted (HTML) text of a confession/reply. Old backups only have plain text."""
    return item.get("html") or esc(item["text"])


def original_preview(conf):
    """Short version of a confession for the admin reply card (keeps formatting
    when short; plain truncated text when long so tags are never cut in half)."""
    if len(conf["text"]) <= 300:
        return stored_html(conf)
    return esc(conf["text"][:300]) + "…"


def kb(rows):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]
    )


def get_user(uid):
    return state["users"].get(uid)


def touch_user(tg_user):
    u = state["users"].setdefault(tg_user.id, {"user_id": tg_user.id})
    if u.get("username") != tg_user.username or u.get("name") != tg_user.full_name:
        u["username"] = tg_user.username
        u["name"] = tg_user.full_name
        mark_dirty()
    return u


def profile_complete(u):
    return bool(u and u.get("gender") and u.get("class") and u.get("grp")
                and u.get("allow_replies") is not None)


def label(u):
    grp = LABEL_HIDDEN_GROUP if u["grp"] == "Hidden" else u["grp"]
    return LABEL_FORMAT.format(gender=u["gender"], cls=u["class"], grp=grp)


async def safe_send(ctx, chat_id, text, html=False):
    if not text:  # silent: UI text set to None/empty
        return
    try:
        await ctx.bot.send_message(
            chat_id, text, parse_mode=ParseMode.HTML if html else None
        )
    except Exception as e:
        log.warning("Could not message %s: %s", chat_id, e)


# -------------------------------------------------------------- ONBOARDING
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    u = touch_user(update.effective_user)
    u.update({"gender": None, "class": None, "grp": None, "allow_replies": None})
    mark_dirty()
    await update.message.reply_text(
        TXT_WELCOME,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[(t, f"g:{v}") for t, v in GENDER_OPTIONS]]),
    )


async def onboarding_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u = touch_user(q.from_user)
    kind, _, val = q.data.partition(":")
    await q.answer()

    if kind == "g":
        u["gender"] = val
        await q.edit_message_text(
            TXT_ASK_CLASS,
            reply_markup=kb([[(t, f"c:{v}") for t, v in CLASS_OPTIONS]]),
        )
    elif kind == "c":
        u["class"] = val
        rows = [[(g, f"grp:{g}") for g in GROUPS[i:i + 3]]
                for i in range(0, len(GROUPS), 3)]
        rows.append([(BTN_HIDDEN_GROUP, "grp:Hidden")])
        await q.edit_message_text(TXT_ASK_GROUP, reply_markup=kb(rows))
    elif kind == "grp":
        u["grp"] = val
        await q.edit_message_text(
            TXT_ASK_REPLIES,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[(BTN_ALLOW_REPLIES, "pr:1"),
                              (BTN_DENY_REPLIES, "pr:0")]]),
        )
    elif kind == "pr":
        u["allow_replies"] = int(val)
        await q.edit_message_text(TXT_SETUP_DONE, parse_mode=ParseMode.MARKDOWN)
    mark_dirty()


# ------------------------------------------------------- MESSAGE HANDLING
def reply_target_error(sender, cid):
    """Returns an error text if `sender` can't reply to confession `cid`, else None."""
    conf = state["confessions"].get(cid)
    if not conf or conf["status"] != "approved":
        return TXT_CONFESSION_NOT_FOUND.format(cid=cid)
    owner = get_user(conf["user_id"])
    if not owner or not owner.get("allow_replies"):
        return TXT_REPLIES_DISABLED.format(cid=cid)
    if conf["user_id"] == sender:
        return TXT_OWN_CONFESSION
    return None


async def begin_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE, cid: int):
    """Validate the target confession, then ask for the reply text."""
    err = reply_target_error(update.effective_user.id, cid)
    if err:
        await update.message.reply_text(err)
        return
    ctx.user_data["reply_to"] = cid
    await update.message.reply_text(TXT_ASK_REPLY_TEXT.format(cid=cid))


async def reply_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/reply  -> asks for the number, then for the reply text.
    /reply 5 -> skips straight to asking for the reply text."""
    if update.effective_chat.type != "private":
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


async def private_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    u = get_user(msg.from_user.id)
    if not profile_complete(u):
        await msg.reply_text(TXT_NEED_START)
        return
    touch_user(msg.from_user)

    plain = msg.text.strip()
    html = msg.text_html.strip()   # keeps bold / italic / links / etc.

    # --- step 1 of /reply: waiting for the confession number ---
    if ctx.user_data.get("awaiting_number"):
        m = NUMBER_RE.match(plain)
        if not m:
            await msg.reply_text(TXT_BAD_NUMBER)
            return
        ctx.user_data.pop("awaiting_number", None)
        await begin_reply(update, ctx, int(m.group(1)))
        return

    # --- quick reply in one message:  T5 your reply ---
    m = REPLY_RE.match(plain)
    if m:
        cid, body_plain = int(m.group(1)), m.group(2).strip()
        if not body_plain:
            await begin_reply(update, ctx, cid)
            return
        mh = REPLY_RE.match(html)  # same split on the formatted version
        body_html = mh.group(2).strip() if mh else esc(body_plain)
        await submit_reply(update, cid, body_plain, body_html)
        return

    # --- step 2 of /reply: waiting for the reply text ---
    pending = ctx.user_data.get("reply_to")
    if pending:
        ctx.user_data.pop("reply_to", None)
        await submit_reply(update, pending, plain, html)
        return

    await submit_confession(update, ctx, u, plain, html)


async def submit_confession(update, ctx, u, plain, html):
    if len(plain) > MAX_LEN:
        await update.message.reply_text(TXT_TOO_LONG.format(max=MAX_LEN))
        return
    # No awaits between reading and incrementing the counter, so two people
    # writing at the same moment always get different numbers.
    cid = state["next_confession"]
    state["next_confession"] += 1
    state["confessions"][cid] = {
        "id": cid, "user_id": u["user_id"], "text": plain, "html": html,
        "status": "pending", "created": time.time(),
    }
    mark_dirty()

    await ctx.bot.send_message(
        ADMIN_GROUP_ID,
        TXT_ADMIN_NEW_CONFESSION.format(
            cid=cid, label=esc(label(u)), text=html,
            replies=TXT_REPLIES_ON if u["allow_replies"] else TXT_REPLIES_OFF,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=kb([[(BTN_APPROVE, f"ac:{cid}"), (BTN_REJECT, f"rc:{cid}")]]),
    )
    await update.message.reply_text(
        TXT_CONFESSION_RECEIVED.format(cid=cid), parse_mode=ParseMode.MARKDOWN
    )


async def submit_reply(update, cid, plain, html):
    sender = update.message.from_user.id
    err = reply_target_error(sender, cid)
    if err:
        await update.message.reply_text(err)
        return
    if len(plain) > MAX_LEN:
        await update.message.reply_text(TXT_TOO_LONG.format(max=MAX_LEN))
        return
    conf = state["confessions"][cid]

    rid = state["next_reply"]
    state["next_reply"] += 1
    state["replies"][rid] = {
        "id": rid, "confession_id": cid, "from_user": sender,
        "text": plain, "html": html,
        "status": "pending", "created": time.time(),
    }
    mark_dirty()

    await update.get_bot().send_message(
        ADMIN_GROUP_ID,
        TXT_ADMIN_NEW_REPLY.format(
            rid=rid, cid=cid, label=esc(label(get_user(sender))),
            original=original_preview(conf), text=html,
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=kb([[(BTN_APPROVE, f"ar:{rid}"), (BTN_REJECT, f"rr:{rid}")]]),
    )
    await update.message.reply_text(TXT_REPLY_SENT_FOR_REVIEW.format(cid=cid))


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("reply_to", None)
    ctx.user_data.pop("awaiting_number", None)
    await update.message.reply_text(TXT_CANCELLED)


# ----------------------------------------------------------- ADMIN BUTTONS
async def admin_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.message.chat.id != ADMIN_GROUP_ID:
        await q.answer(TXT_NOT_ADMIN_GROUP, show_alert=True)
        return
    action, _, sid = q.data.partition(":")
    sid = int(sid)
    admin = q.from_user.first_name
    approve = action in ("ac", "ar")

    if action in ("ac", "rc"):
        row = state["confessions"].get(sid)
        if not row or row["status"] != "pending":
            await q.answer(TXT_ALREADY_HANDLED, show_alert=True)
            return
        row["status"] = "approved" if approve else "rejected"
        mark_dirty()
        owner = get_user(row["user_id"])
        if approve:
            post = TXT_CHANNEL_POST.format(
                cid=sid, label=esc(label(owner)), text=stored_html(row)
            )
            if owner.get("allow_replies"):
                post += TXT_CHANNEL_REPLY_HINT.format(cid=sid)
            post += TXT_CHANNEL_FOOTER
            try:
                await ctx.bot.send_message(CHANNEL_ID, post, parse_mode=ParseMode.HTML)
                note = TXT_CONF_APPROVED_PUBLISHED.format(cid=sid)
            except TelegramError as e:
                log.error("Channel post failed: %s", e)
                note = TXT_CONF_APPROVED.format(cid=sid)
                await q.message.reply_text(TXT_CHANNEL_FAIL_WARNING.format(cid=sid))
        else:
            note = fmt(TXT_CONF_REJECTED, cid=sid)
        await safe_send(ctx, row["user_id"], note)

    else:
        row = state["replies"].get(sid)
        if not row or row["status"] != "pending":
            await q.answer(TXT_ALREADY_HANDLED, show_alert=True)
            return
        row["status"] = "approved" if approve else "rejected"
        mark_dirty()
        conf = state["confessions"][row["confession_id"]]
        if approve:
            await safe_send(
                ctx, conf["user_id"],
                TXT_REPLY_DELIVERED_TO_OWNER.format(cid=conf["id"], text=stored_html(row)),
                html=True,
            )
            await safe_send(ctx, row["from_user"],
                            fmt(TXT_REPLY_DELIVERED_TO_SENDER, cid=conf["id"]))
        else:
            await safe_send(ctx, row["from_user"],
                            fmt(TXT_REPLY_REJECTED_TO_SENDER, cid=conf["id"]))

    verdict = TXT_VERDICT_APPROVED if approve else TXT_VERDICT_REJECTED
    await q.edit_message_text(
        f"{q.message.text_html}\n\n"
        + TXT_VERDICT_LINE.format(verdict=verdict, admin=esc(admin)),
        parse_mode=ParseMode.HTML,
    )
    await q.answer(TXT_OK_TOAST)


async def chat_id_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TXT_CHAT_ID.format(id=update.effective_chat.id))


# -------------------------------------------------------------------- MAIN
def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(on_start)
        .post_stop(on_stop)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("chatid", chat_id_cmd))
    app.add_handler(CallbackQueryHandler(onboarding_cb, pattern=r"^(g|c|grp|pr):"))
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^(ac|rc|ar|rr):"))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
                       private_text)
    )
    log.info("Tio is running…")
    app.run_polling()


if __name__ == "__main__":
    main()
