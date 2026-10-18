"""
Tio - Talk It Out!
Anonymous confession bot for Telegram.

Install:  pip install "python-telegram-bot>=20.7"
Run:      BOT_TOKEN=123:ABC python tio_bot.py

Flow
 1. /start -> gender -> class (44/45) -> group (G1-G9 / prefer not to say)
           -> allow private replies? (yes/no)
 2. User sends any text  -> it becomes a confession (T1, T2, ...)
    -> posted in the ADMIN GROUP with Approve / Reject buttons
    -> once approved it is published to CHANNEL_ID (optional) and the
       confessor is notified.
 3. Anyone replies to a confession by sending:   T5 your message here
    (or just "T5", and the bot asks for the message)
    -> only works if the confessor allowed private replies
    -> reply is posted in the ADMIN GROUP for approval
    -> only after approval is it delivered (anonymously) to the confessor.
"""

import logging
import os
import re
import sqlite3
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ------------------------------------------------------------------ CONFIG
# Optional: if python-dotenv is installed, a local .env file is loaded
# (put BOT_TOKEN=... in it and never commit it to git).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# The token is NEVER stored in the code - it must come from the environment.
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit(
        "BOT_TOKEN is not set. Set it as an environment variable "
        "(or in a .env file) before running the bot."
    )

ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-5370857010"))
# Channel where approved confessions are published
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1004439548910"))
DB_PATH = os.environ.get("DB_PATH", "tio.db")

GROUPS = [f"G{i}" for i in range(1, 10)]
REPLY_RE = re.compile(r"^\s*[Tt](\d+)\b\s*(.*)$", re.DOTALL)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("tio")


# ---------------------------------------------------------------------- DB
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users(
                user_id INTEGER PRIMARY KEY,
                gender TEXT, class TEXT, grp TEXT,
                allow_replies INTEGER
            );
            CREATE TABLE IF NOT EXISTS confessions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, text TEXT,
                status TEXT DEFAULT 'pending', created REAL
            );
            CREATE TABLE IF NOT EXISTS replies(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                confession_id INTEGER, from_user INTEGER, text TEXT,
                status TEXT DEFAULT 'pending', created REAL
            );
            """
        )


def get_user(uid):
    with db() as c:
        return c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()


def upsert_user(uid, **fields):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
        for k, v in fields.items():
            c.execute(f"UPDATE users SET {k}=? WHERE user_id=?", (v, uid))


def profile_complete(u):
    return u and u["gender"] and u["class"] and u["grp"] and u["allow_replies"] is not None


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# -------------------------------------------------------------- ONBOARDING
def kb(rows):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]
    )


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    upsert_user(update.effective_user.id, gender=None, **{"class": None}, grp=None,
                allow_replies=None)
    await update.message.reply_text(
        "👋 Welcome to *Tio — Talk It Out!*\n"
        "Write your confession anonymously.\n\n"
        "First, are you:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb([[("👨 Male", "g:Male"), ("👩 Female", "g:Female")]]),
    )


async def onboarding_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    kind, _, val = q.data.partition(":")
    await q.answer()

    if kind == "g":
        upsert_user(uid, gender=val)
        await q.edit_message_text(
            "Which class are you in?",
            reply_markup=kb([[("Class 44", "c:44"), ("Class 45", "c:45")]]),
        )
    elif kind == "c":
        upsert_user(uid, **{"class": val})
        rows = [[(g, f"grp:{g}") for g in GROUPS[i:i + 3]] for i in range(0, 9, 3)]
        rows.append([("🤐 Prefer not to say", "grp:Hidden")])
        await q.edit_message_text("Which group are you in?", reply_markup=kb(rows))
    elif kind == "grp":
        upsert_user(uid, grp=val)
        await q.edit_message_text(
            "Allow *private replies*?\n"
            "Other users can answer your confession by sending its number "
            "(e.g. `T12 your message`). Every reply is reviewed by admins "
            "before it reaches you.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb([[("✅ Allow", "pr:1"), ("🚫 Don't allow", "pr:0")]]),
        )
    elif kind == "pr":
        upsert_user(uid, allow_replies=int(val))
        await q.edit_message_text(
            "🎉 You're all set!\n\n"
            "✍️ Just send me your confession as a message.\n"
            "💬 To reply to someone: `T5 your reply` (their confession number).\n"
            "🔁 /start to change your info.",
            parse_mode=ParseMode.MARKDOWN,
        )


# ------------------------------------------------------- MESSAGE HANDLING
def label(u):
    grp = "Group hidden" if u["grp"] == "Hidden" else u["grp"]
    return f"{u['gender']} • Class {u['class']} • {grp}"


async def private_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = msg.from_user.id
    u = get_user(uid)
    if not profile_complete(u):
        await msg.reply_text("Please press /start first to set up your profile.")
        return

    text = msg.text.strip()

    # --- user is answering a "T5" prompt ---
    pending = ctx.user_data.get("reply_to")
    m = REPLY_RE.match(text)

    if m:
        cid, body = int(m.group(1)), m.group(2).strip()
        if not body:
            ctx.user_data["reply_to"] = cid
            await msg.reply_text(f"✍️ Send your reply to T{cid} now (or /cancel).")
            return
        await submit_reply(update, ctx, cid, body)
        return

    if pending:
        ctx.user_data.pop("reply_to", None)
        await submit_reply(update, ctx, pending, text)
        return

    await submit_confession(update, ctx, u, text)


async def submit_confession(update, ctx, u, text):
    with db() as c:
        cur = c.execute(
            "INSERT INTO confessions(user_id,text,created) VALUES(?,?,?)",
            (u["user_id"], text, time.time()),
        )
        cid = cur.lastrowid

    await ctx.bot.send_message(
        ADMIN_GROUP_ID,
        f"📩 <b>New confession T{cid}</b>\n"
        f"<i>{esc(label(u))} • replies "
        f"{'ON' if u['allow_replies'] else 'OFF'}</i>\n\n{esc(text)}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb([[("✅ Approve", f"ac:{cid}"), ("❌ Reject", f"rc:{cid}")]]),
    )
    await update.message.reply_text(
        f"✅ Your confession was received as *T{cid}* and is waiting for approval.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def submit_reply(update, ctx, cid, body):
    sender = update.message.from_user.id
    with db() as c:
        conf = c.execute("SELECT * FROM confessions WHERE id=?", (cid,)).fetchone()
    if not conf or conf["status"] != "approved":
        await update.message.reply_text(f"❌ Confession T{cid} doesn't exist.")
        return
    owner = get_user(conf["user_id"])
    if not owner or not owner["allow_replies"]:
        await update.message.reply_text(
            f"🚫 The author of T{cid} doesn't allow private replies."
        )
        return
    if conf["user_id"] == sender:
        await update.message.reply_text("You can't reply to your own confession 🙂")
        return

    sender_u = get_user(sender)
    with db() as c:
        rid = c.execute(
            "INSERT INTO replies(confession_id,from_user,text,created) VALUES(?,?,?,?)",
            (cid, sender, body, time.time()),
        ).lastrowid

    await ctx.bot.send_message(
        ADMIN_GROUP_ID,
        f"💬 <b>Reply R{rid} → T{cid}</b>\n"
        f"<i>From: {esc(label(sender_u))}</i>\n\n"
        f"<b>Original:</b> {esc(conf['text'][:300])}\n\n"
        f"<b>Reply:</b> {esc(body)}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb([[("✅ Approve", f"ar:{rid}"), ("❌ Reject", f"rr:{rid}")]]),
    )
    await update.message.reply_text(
        f"✅ Your reply to T{cid} was sent for approval before delivery."
    )


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("reply_to", None)
    await update.message.reply_text("Cancelled.")


# ----------------------------------------------------------- ADMIN BUTTONS
async def admin_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.message.chat.id != ADMIN_GROUP_ID:
        await q.answer("Not allowed.", show_alert=True)
        return
    action, _, sid = q.data.partition(":")
    sid = int(sid)
    admin = q.from_user.first_name
    approve = action in ("ac", "ar")

    if action in ("ac", "rc"):
        with db() as c:
            row = c.execute("SELECT * FROM confessions WHERE id=?", (sid,)).fetchone()
            if not row or row["status"] != "pending":
                await q.answer("Already handled.", show_alert=True)
                return
            c.execute("UPDATE confessions SET status=? WHERE id=?",
                      ("approved" if approve else "rejected", sid))
        owner = get_user(row["user_id"])
        if approve:
            if CHANNEL_ID:
                await ctx.bot.send_message(
                    CHANNEL_ID,
                    f"<b>T{sid}</b>\n<i>{esc(label(owner))}</i>\n\n{esc(row['text'])}"
                    + ("\n\n💬 Reply privately by sending T%d + your message to the bot."
                       % sid if owner["allow_replies"] else ""),
                    parse_mode=ParseMode.HTML,
                )
            note = f"✅ Your confession T{sid} was approved" + (
                " and published." if CHANNEL_ID else ".")
        else:
            note = f"❌ Your confession T{sid} was not approved."
        await safe_send(ctx, row["user_id"], note)

    else:  # replies
        with db() as c:
            row = c.execute("SELECT * FROM replies WHERE id=?", (sid,)).fetchone()
            if not row or row["status"] != "pending":
                await q.answer("Already handled.", show_alert=True)
                return
            c.execute("UPDATE replies SET status=? WHERE id=?",
                      ("approved" if approve else "rejected", sid))
            conf = c.execute("SELECT * FROM confessions WHERE id=?",
                             (row["confession_id"],)).fetchone()
        if approve:
            await safe_send(
                ctx, conf["user_id"],
                f"💌 <b>Anonymous reply to your confession T{conf['id']}:</b>\n\n"
                f"{esc(row['text'])}",
                html=True,
            )
            await safe_send(ctx, row["from_user"],
                            f"✅ Your reply to T{conf['id']} was delivered.")
        else:
            await safe_send(ctx, row["from_user"],
                            f"❌ Your reply to T{conf['id']} was not approved.")

    verdict = "✅ APPROVED" if approve else "❌ REJECTED"
    await q.edit_message_text(
        f"{q.message.text_html}\n\n<b>{verdict}</b> by {esc(admin)}",
        parse_mode=ParseMode.HTML,
    )
    await q.answer("Done")


async def safe_send(ctx, chat_id, text, html=False):
    try:
        await ctx.bot.send_message(
            chat_id, text, parse_mode=ParseMode.HTML if html else None
        )
    except Exception as e:  # user blocked the bot, etc.
        log.warning("Could not message %s: %s", chat_id, e)


async def chat_id_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Run /chatid inside your admin group to see its real ID."""
    await update.message.reply_text(f"Chat ID: {update.effective_chat.id}")


# -------------------------------------------------------------------- MAIN
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
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
