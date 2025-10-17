# bot/run_admin_bot.py
import os, sys, re, time, asyncio, logging
from typing import List, Tuple
import httpx

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# ==================== ENV ====================
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
API     = os.getenv("SLH_API_BASE","http://127.0.0.1:8000").rstrip("/")
ADMINS  = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip().isdigit()]
MODE    = os.getenv("BOT_MODE","webhook").lower().strip()          # webhook | polling
PUBLIC  = os.getenv("BOT_WEBHOOK_PUBLIC_BASE","").rstrip("/")      # e.g. https://slhbot-bot.up.railway.app
PATH    = os.getenv("BOT_WEBHOOK_PATH","/tg")                      # e.g. /tg
SECRET  = os.getenv("BOT_WEBHOOK_SECRET","sela_secret_123")
PORT    = int(os.getenv("BOT_PORT", os.getenv("PORT","8080")))     # Railway exposes $PORT

DEFAULT_WALLET   = os.getenv("DEFAULT_WALLET","").strip()
DEFAULT_META_CID = os.getenv("DEFAULT_META_CID","").strip()
SELA_AMOUNT      = os.getenv("SELA_AMOUNT","0.15984").strip()

if not TOKEN:
    print("TELEGRAM_BOT_TOKEN missing"); sys.exit(1)
if MODE == "webhook":
    if not PUBLIC.startswith("https://"):
        print("BOT_WEBHOOK_PUBLIC_BASE must start with https:// in webhook mode")
        sys.exit(1)

# Telegram restriction for secret
if not re.fullmatch(r"[A-Za-z0-9_\-]+", SECRET):
    print("BOT_WEBHOOK_SECRET must contain only letters/digits/_/-")
    sys.exit(1)

# ==================== Logging ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s"
)
log = logging.getLogger("slh.bot")

log.info("===== SLH Admin Bot – Startup =====")
log.info(f"MODE: {MODE}")
log.info(f"API: {API}")
log.info(f"PUBLIC: {PUBLIC if PUBLIC else '-'}")
log.info(f"PATH: {PATH}")
log.info(f"PORT: {PORT}")
log.info(f"SECRET(valid): {bool(re.fullmatch(r'[A-Za-z0-9_\\-]+', SECRET))}")
log.info(f"ADMINS: {'(unset -> allow self)' if not ADMINS else ','.join(map(str,ADMINS))}")
log.info(f"DEFAULT_WALLET: {DEFAULT_WALLET or '-'}")
log.info(f"DEFAULT_META_CID: {DEFAULT_META_CID or '-'}")
log.info(f"SELA_AMOUNT: {SELA_AMOUNT}")
log.info(f"TOKEN(masked): {TOKEN[:6]}...{TOKEN[-6:]}")

# ==================== Helpers ====================
def is_admin(user_id:int) -> bool:
    return (user_id in ADMINS) if ADMINS else True  # אם לא הוגדר – נאפשר לצורך בדיקות

async def api_post(path:str, payload:dict):
    url = f"{API}{path}"
    timeout = httpx.Timeout(20, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as cx:
        r = await cx.post(url, json=payload)
        r.raise_for_status()
        return r.json()

EVENTS: List[dict] = []
def push_event(ev:dict):
    ev = dict({"ts": int(time.time())}, **ev)
    EVENTS.append(ev)
    if len(EVENTS) > 500:
        del EVENTS[:200]

SUMMARY_MD = (
    "*SLH – Go-Live Pack (Testnet)*\n\n"
    "*0) Quick Ref*\n"
    "• Network: BSC Testnet (97)\n"
    "• NFT: `0x8AD1de67648dB44B1b1D0E3475485910CedDe90b`\n"
    "• Example CID: `QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq`\n"
)

# ==================== Handlers ====================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    who = update.effective_user
    await update.message.reply_text(
        f"שלום {who.first_name or ''}! הבוט באוויר ✅\nנסה /ping או /adm_help"
    )

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")

async def adm_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    txt = (
        "פקודות אדמין שימושיות:\n"
        "/adm_status — מצב ריצה והגדרות\n"
        "/adm_setwebhook — קובע webhook לפי ההגדרות הנוכחיות\n"
        "/adm_recent [N] — האירועים האחרונים\n"
        "/adm_sell <wallet> <ipfs://CID|https://...> [note]\n"
        "/adm_echo <טקסט> — החזר טקסט (בדיקה)\n"
        "/ping — בדיקת חיים\n"
    )
    await update.message.reply_text(txt)

async def adm_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = (
        "Status:\n\n"
        f"MODE={MODE} | PORT={PORT} | PUBLIC='{PUBLIC}' | PATH='{PATH}' | SECRET.len={len(SECRET)} | API='{API}'"
    )
    await update.message.reply_text(msg)

async def adm_setwebhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    ok, info = await ensure_webhook()
    if ok:
        await update.message.reply_text("SetWebhook → True\n" + info)
    else:
        await update.message.reply_text("SetWebhook → False\n" + info)

async def adm_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    n = 20
    if context.args and context.args[0].isdigit():
        n = min(int(context.args[0]), 100)
    lines = []
    for ev in EVENTS[-n:]:
        lines.append(
            f"ts={ev.get('ts')} | wallet={ev.get('wallet','-')} | tokenURI={ev.get('token_uri','-')}\n"
            f"mint={ev.get('mint_tx','-')} | sela={ev.get('sela_tx','-')} | note={ev.get('note','-')}"
        )
    if not lines:
        await update.message.reply_text("No events yet.")
    else:
        await update.message.reply_text("```\n" + "\n\n".join(lines) + "\n```", parse_mode="Markdown")

async def adm_echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    txt = " ".join(context.args) if context.args else "(no text)"
    await update.message.reply_text(f"echo: {txt}")

async def adm_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /adm_sell <wallet> <ipfs://CID|https://...> [note...]")
        return
    wallet = args[0].strip()
    uri_in  = args[1].strip()
    note = " ".join(args[2:]).strip() if len(args) > 2 else ""

    # normalize token_uri
    if uri_in.startswith("ipfs://"):
        token_uri = uri_in
    elif re.match(r"^Qm[1-9A-Za-z]{44,}", uri_in):  # raw CID
        token_uri = f"ipfs://{uri_in}"
    else:
        token_uri = uri_in  # allow https

    try:
        # 1) Mint
        mint_res = await api_post("/v1/chain/mint-demo", {
            "to_wallet": wallet,
            "token_uri": token_uri
        })
        mint_tx = mint_res.get("tx") or mint_res.get("hash") or "-"

        # 2) Grant SELA
        sela_amt = SELA_AMOUNT
        grant_res = await api_post("/v1/chain/grant-sela", {
            "to_wallet": wallet,
            "amount": str(sela_amt)
        })
        sela_tx = grant_res.get("tx") or grant_res.get("hash") or "-"

        push_event({
            "wallet": wallet,
            "token_uri": token_uri,
            "mint_tx": mint_tx,
            "sela_tx": sela_tx,
            "note": note
        })

        msg = (
            "✅ *Sold + Granted*\n"
            f"• Wallet: `{wallet}`\n"
            f"• tokenURI: `{token_uri}`\n"
            f"• Mint TX: `{mint_tx}`\n"
            f"• SELA TX: `{sela_tx}`\n"
        )
        await update.message.reply_markdown(msg)

    except httpx.HTTPError as e:
        await update.message.reply_text(f"API error: {e}")
    except Exception as e:
        await update.message.reply_text(f"Unexpected: {e}")

async def echo_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # לוג כללי לכל הודעה שמגיעה — עוזר בדיבוג webhook
    try:
        chat_id = update.effective_chat.id if update.effective_chat else "?"
        uid     = update.effective_user.id if update.effective_user else "?"
        txt     = update.message.text if update.message else "<no text>"
        log.info(f"[UPDATE] chat={chat_id} user={uid} text={txt}")
    except Exception:
        pass

    if update.message and update.message.text and update.message.text.startswith("/"):
        await update.message.reply_text("Unknown command. Try /adm_help")
    else:
        if update.effective_chat and str(update.effective_chat.type) == "ChatType.PRIVATE":
            await update.message.reply_text("היי! /adm_help")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Exception while handling an update:", exc_info=context.error)

# ==================== Webhook bootstrap ====================
async def ensure_webhook() -> Tuple[bool,str]:
    """קובע Webhook בתחילת ריצה — ומחזיר (ok, info_text)."""
    url = f"{PUBLIC}{PATH}"
    try:
        timeout = httpx.Timeout(20, connect=10)
        async with httpx.AsyncClient(timeout=timeout) as cx:
            delr = await cx.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
            setr = await cx.post(
                f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                data={"url": url, "secret_token": SECRET}
            )
            infor = await cx.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")

        ok = bool(setr.json().get("ok"))
        log.info("ensure_webhook: ok=%s", ok)
        log.info("url=%s", url)
        log.info("delete=%s", delr.json())
        log.info("set=%s", setr.json())
        log.info("info=%s", infor.json())
        info_text = url
        return ok, info_text
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

# ==================== App wiring ====================
def build_app():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ping",  ping_cmd))
    app.add_handler(CommandHandler("adm_help", adm_help))
    app.add_handler(CommandHandler("adm_status", adm_status))
    app.add_handler(CommandHandler("adm_setwebhook", adm_setwebhook))
    app.add_handler(CommandHandler("adm_recent", adm_recent))
    app.add_handler(CommandHandler("adm_echo", adm_echo))
    app.add_handler(CommandHandler("adm_sell", adm_sell))
    app.add_handler(MessageHandler(filters.ALL, echo_fallback))
    app.add_error_handler(error_handler)
    return app

def run_polling(app):
    log.info("Starting bot in POLLING mode…")
    app.run_polling(close_loop=False)

def run_webhook(app):
    """
    חשוב: url_path חייב להתאים בדיוק למסלול שבו טלגרם תגיע.
    אם PATH='/tg' → צריך url_path='tg'
    """
    if not PUBLIC.startswith("https://"):
        print("BOT_WEBHOOK_PUBLIC_BASE must be https for webhook mode")
        sys.exit(1)

    url = f"{PUBLIC}{PATH}"
    url_path = PATH.lstrip("/")  # *** זו הייתה הבעיה ***

    log.info(f"Starting bot in WEBHOOK mode at {url} (port {PORT})")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=url_path,                # <— מסלול פנימי לשרת
        webhook_url=url,                  # <— ה־URL המלא שטלגרם תקרא אליו
        secret_token=SECRET,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False,
        cert=None, key=None
    )

# ==================== Main ====================
if __name__ == "__main__":
    # קובעים webhook בתחילת ריצה (כמו health-check)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ok, info = loop.run_until_complete(ensure_webhook())
        if not ok:
            log.warning("ensure_webhook failed: %s", info)
    except Exception as e:
        log.warning("ensure_webhook error: %s", e)

    print(f"🚀 Admin bot is starting ({MODE})…")
    application = build_app()
    if MODE == "polling":
        run_polling(application)
    else:
        run_webhook(application)
