# -*- coding: utf-8 -*-
"""
SLH Admin Bot — Railway-ready
- Webhook first (https only), falls back to polling אוטומטית כשצריך
- לוגים קריאים + הדפסות דיבאג ידידותיות
- פקודות בסיס: /start /ping /adm_help /adm_status /adm_setwebhook /adm_echo
- דרישות: python-telegram-bot>=21  (ול־webhooks: pip install "python-telegram-bot[webhooks]")
"""

import os
import sys
import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import BadRequest

# ---------- Logging ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
# הפחתת רעש ספריות רשת
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("slh.bot")

# ---------- ENV ----------
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API     = os.getenv("SLH_API_BASE", "").rstrip("/")
MODE    = os.getenv("BOT_MODE", "webhook").strip().lower()     # webhook | polling
PUBLIC  = os.getenv("BOT_WEBHOOK_PUBLIC_BASE", "").strip().rstrip("/")  # https://your-domain
PATH    = os.getenv("BOT_WEBHOOK_PATH", "/tg").strip()
SECRET  = os.getenv("BOT_WEBHOOK_SECRET", "sela_secret").strip()

# Railway exposes PORT; אם לא — קח BOT_PORT; אחרת 8081
_port_env = os.getenv("PORT") or os.getenv("BOT_PORT") or "8081"
try:
    PORT = int(_port_env)
except ValueError:
    logger.warning("BOT_PORT/PORT invalid (%s). Using 8081.", _port_env)
    PORT = 8081

# Railway לפעמים חושף דומיין ציבורי במשתנה סביבה:
RAILWAY_PUBLIC_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
if not PUBLIC and RAILWAY_PUBLIC_DOMAIN:
    PUBLIC = f"https://{RAILWAY_PUBLIC_DOMAIN}"
    logger.info("BOT_WEBHOOK_PUBLIC_BASE not set, derived from RAILWAY_PUBLIC_DOMAIN=%s", PUBLIC)

def _mode_summary() -> str:
    return (
        f"MODE={MODE} | PORT={PORT} | PUBLIC='{PUBLIC or '-'}' "
        f"| PATH='{PATH}' | SECRET.len={len(SECRET)} | API='{API or '-'}'"
    )

# ---------- Handlers ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    who = update.effective_user
    await update.message.reply_text(
        f"שלום {who.first_name or ''}! הבוט באוויר ✅\n"
        f"נסה /ping או /adm_help"
    )

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")

async def adm_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "פקודות אדמין שימושיות:\n"
        "/adm_status — מצב ריצה והגדרות\n"
        "/adm_setwebhook — קובע webhook לפי ההגדרות הנוכחיות\n"
        "/adm_echo <טקסט> — החזר טקסט (בדיקה)\n"
        "/ping — בדיקת חיים\n"
    )
    await update.message.reply_text(text)

async def adm_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Status:\n```\n" + _mode_summary() + "\n```",
        parse_mode="Markdown"
    )

async def adm_setwebhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מגדיר מחדש webhook לפי ה־env הנוכחיים. שימושי אחרי שינוי דומיין."""
    if not PUBLIC.startswith("https://"):
        await update.message.reply_text("❌ PUBLIC URL חייב להיות https. קבע BOT_WEBHOOK_PUBLIC_BASE=HTTPS…")
        return
    url = f"{PUBLIC}{PATH}"
    try:
        ok = await context.bot.set_webhook(url=url, secret_token=SECRET)
    except BadRequest as e:
        await update.message.reply_text(f"❌ Telegram error: {e.message}")
        return
    await update.message.reply_text(f"SetWebhook → {ok}\n{url}")

async def adm_echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = " ".join(context.args) if context.args else "(no text)"
    await update.message.reply_text(f"echo: {msg}")

async def fallback_logger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """לוג כללי לכל מה שלא נתפס; עוזר בדיבאג."""
    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None
    txt = update.message.text if update.message else "<no text>"
    logger.info("[UPDATE] chat=%s user=%s text=%s", chat_id, user_id, txt)

# ---------- App builder ----------

def build_app() -> Application:
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing")
        sys.exit(1)

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("adm_help", adm_help))
    app.add_handler(CommandHandler("adm_status", adm_status))
    app.add_handler(CommandHandler("adm_setwebhook", adm_setwebhook))
    app.add_handler(CommandHandler("adm_echo", adm_echo))
    app.add_handler(MessageHandler(filters.ALL, fallback_logger))

    return app

# ---------- Runners ----------

async def run_polling(app: Application):
    logger.warning("Running in POLLING mode. " + _mode_summary())
    await app.initialize()
    try:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Polling started ✅")
        # רץ עד Ctrl+C
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

async def run_webhook(app: Application):
    if not PUBLIC.startswith("https://"):
        logger.error("BOT_WEBHOOK_PUBLIC_BASE must be https for webhook mode")
        sys.exit(1)

    url = f"{PUBLIC}{PATH}"
    logger.info("Starting WEBHOOK. " + _mode_summary())
    await app.initialize()
    try:
        # קובע webhook בטלגרם עם secret
        await app.bot.set_webhook(url=url, secret_token=SECRET)
        logger.info("Webhook set ✅ %s", url)

        await app.start()
        # מאזין HTTP פנימי על ה־PORT שריילוואי פותח לנו
        await app.updater.start_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=PATH,
            webhook_url=url,
            secret_token=SECRET,
            drop_pending_updates=True,
        )
        logger.info("Webhook listener up on port %s ✅", PORT)
        await asyncio.Event().wait()
    except BadRequest as e:
        logger.error("Telegram BadRequest: %s", e)
        raise
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

def main():
    logger.info("Booting Admin bot…")
    app = build_app()

    if MODE == "webhook":
        try:
            asyncio.run(run_webhook(app))
        except SystemExit:
            raise
        except Exception:
            # נפילה בוובהוק? ננסה polling כדי שלא תישאר בלי בוט בזמן דיבאג.
            logger.exception("Webhook failed — falling back to POLLING.")
            asyncio.run(run_polling(app))
    else:
        asyncio.run(run_polling(app))

if __name__ == "__main__":
    main()
