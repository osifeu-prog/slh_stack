import os, sys, logging, asyncio, time, re
from typing import List
import httpx

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

# ===== Env =====
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
API     = os.getenv("SLH_API_BASE","http://127.0.0.1:8000").rstrip("/")
ADMINS  = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip().isdigit()]
MODE    = os.getenv("BOT_MODE","webhook").lower().strip()  # webhook | polling
PUBLIC  = os.getenv("BOT_WEBHOOK_PUBLIC_BASE","").rstrip("/")
PATH    = os.getenv("BOT_WEBHOOK_PATH","/tg")
SECRET  = os.getenv("BOT_WEBHOOK_SECRET","sela_secret_123")
PORT    = int(os.getenv("PORT", os.getenv("BOT_PORT","8080")))

DEFAULT_WALLET   = os.getenv("DEFAULT_WALLET","").strip()
DEFAULT_META_CID = os.getenv("DEFAULT_META_CID","").strip()
SELA_AMOUNT      = os.getenv("SELA_AMOUNT","0.15984").strip()

# ===== Logging =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s"
)
log = logging.getLogger("slh.bot")

def mask_token(tok: str) -> str:
    if not tok: return "<empty>"
    if len(tok) <= 8: return "***"
    return f"{tok[:6]}...{tok[-6:]}"

def secret_is_valid(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_\-]+", s))

# ===== Helpers =====
def is_admin(user_id:int) -> bool:
    return (user_id in ADMINS) if ADMINS else True  # if unset, allow for dev

async def api_post(path:str, payload:dict):
    url = f"{API}{path}"
    timeout = httpx.Timeout(20, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as cx:
        r = await cx.post(url, json=payload)
        r.raise_for_status()
        return r.json()

# simple in-process event log
EVENTS: List[dict] = []

def push_event(ev:dict):
    ev2 = dict({"ts": int(time.time())}, **ev)
    EVENTS.append(ev2)
    if len(EVENTS) > 500:
        del EVENTS[:200]

SUMMARY_MD = (
    "*SLH – Go-Live Pack (Testnet)*\n\n"
    "*0) Quick Ref*\n"
    "• Network: BSC Testnet (97)\n"
    "• NFT: `0x8AD1de67648dB44B1b1D0E3475485910CedDe90b`\n"
    "• Example CID: `QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq`\n"
)

# ===== Handlers =====
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    who = update.effective_user
    await update.message.reply_text(
        f"שלום {who.first_name or ''}! הבוט באוויר ✅\nנסה /ping או /adm_help"
    )

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")

async def adm_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    txt = (
        "פקודות אדמין שימושיות:\n"
        "/adm_status — מצב ריצה והגדרות\n"
        "/adm_setwebhook — קובע webhook לפי ההגדרות הנוכחיות\n"
        "/adm_echo <טקסט> — החזר טקסט (בדיקה)\n"
        "/adm_post_summary — כרטיס Go-Live\n"
        "/adm_recent [N] — לוג אחרונים\n"
        "/adm_sell <wallet> <ipfs://CID|https://...> [note...] — mint + grant SELA\n"
        "/ping — בדיקת חיים\n"
    )
    await update.message.reply_text(txt)

async def adm_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as cx:
            wh = (await cx.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")).json()
    except Exception as e:
        wh = {"error": str(e)}
    txt = (
        f"Status:\n"
        f"MODE={MODE} | PORT={PORT} | PUBLIC='{PUBLIC}' | PATH='{PATH}'\n"
        f"SECRET.len={len(SECRET)} | SECRET.valid={secret_is_valid(SECRET)}\n"
        f"API='{API}'\n"
        f"WebhookInfo: {wh}"
    )
    await update.message.reply_text(txt)

async def adm_setwebhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    ok, msg = await ensure_webhook()
    await update.message.reply_text(f"SetWebhook → {ok}\n{msg}")

async def adm_echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    txt = " ".join(context.args) if context.args else "(no text)"
    await update.message.reply_text(f"echo: {txt}")

async def adm_post_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_markdown(SUMMARY_MD)

async def adm_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
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
        await update.message.reply_text("אין עדיין אירועים.")
    else:
        await update.message.reply_text("```\n" + "\n\n".join(lines) + "\n```", parse_mode="Markdown")

async def adm_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /adm_sell <wallet> <ipfs://CID|https://...> [note...]")
        return
    wallet = args[0].strip()
    uri_in  = args[1].strip()
    note = " ".join(args[2:]).strip() if len(args) > 2 else ""

    if uri_in.startswith("ipfs://"):
        token_uri = uri_in
    elif re.match(r"^Qm[1-9A-Za-z]{44,}", uri_in):
        token_uri = f"ipfs://{uri_in}"
    else:
        token_uri = uri_in

    try:
        mint_res = await api_post("/v1/chain/mint-demo", {
            "to_wallet": wallet,
            "token_uri": token_uri
        })
        mint_tx = mint_res.get("tx") or mint_res.get("hash") or "-"

        grant_res = await api_post("/v1/chain/grant-sela", {
            "to_wallet": wallet,
            "amount": str(SELA_AMOUNT)
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
    txt = update.message.text if update.message else ""
    if txt.startswith('/'):
        await update.message.reply_text("Unknown command. Try /adm_help")
    else:
        if update.effective_chat and str(update.effective_chat.type) == "ChatType.PRIVATE":
            await update.message.reply_text("Hi! Use /adm_help")

def build_app():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ping",  ping_cmd))
    app.add_handler(CommandHandler("adm_help", adm_help))
    app.add_handler(CommandHandler("adm_status", adm_status))
    app.add_handler(CommandHandler("adm_setwebhook", adm_setwebhook))
    app.add_handler(CommandHandler("adm_echo", adm_echo))
    app.add_handler(CommandHandler("adm_post_summary", adm_post_summary))
    app.add_handler(CommandHandler("adm_recent", adm_recent))
    app.add_handler(CommandHandler("adm_sell", adm_sell))
    app.add_handler(MessageHandler(filters.ALL, echo_fallback))
    return app

async def ensure_webhook():
    if MODE != "webhook":
        return True, "MODE!=webhook (skipping setWebhook)"
    if not PUBLIC.startswith("https://"):
        return False, "BOT_WEBHOOK_PUBLIC_BASE must be https for webhook mode"
    if not secret_is_valid(SECRET):
        return False, "BOT_WEBHOOK_SECRET invalid (allowed: letters/digits/_/-)"
    url = PUBLIC + PATH
    async with httpx.AsyncClient(timeout=10) as cx:
        delw = (await cx.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")).json()
        setw = (await cx.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook", data={
            "url": url, "secret_token": SECRET
        })).json()
        info = (await cx.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")).json()
    ok = bool(setw.get("ok"))
    msg = f"url={url}\ndelete={delw}\nset={setw}\ninfo={info}"
    return ok, msg

def run_polling(app):
    log.info("Starting bot in POLLING mode…")
    app.run_polling(close_loop=False)

def run_webhook(app):
    url = f"{PUBLIC}{PATH}"
    log.info(f"Starting bot in WEBHOOK mode at {url} (port {PORT})")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=url,
        secret_token=SECRET,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False,
        cert=None, key=None
    )

if __name__ == "__main__":
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN missing"); sys.exit(1)

    log.info("===== SLH Admin Bot – Startup =====")
    log.info("MODE: %s", MODE)
    log.info("API: %s", API)
    log.info("PUBLIC: %s", PUBLIC)
    log.info("PATH: %s", PATH)
    log.info("PORT: %s", PORT)
    log.info("SECRET(valid): %s", secret_is_valid(SECRET))
    log.info("ADMINS: %s", "set" if ADMINS else "(unset -> allow self)")
    log.info("DEFAULT_WALLET: %s", DEFAULT_WALLET or "-")
    log.info("DEFAULT_META_CID: %s", DEFAULT_META_CID or "-")
    log.info("SELA_AMOUNT: %s", SELA_AMOUNT)
    log.info("TOKEN(masked): %s", mask_token(TOKEN))

    app = build_app()

    # Auto-ensure webhook on every boot; if it fails -> fallback to polling.
    if MODE == "webhook":
        try:
            ok, msg = asyncio.get_event_loop().run_until_complete(ensure_webhook())
        except RuntimeError:
            # On some hosts the loop is already running; create a new loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ok, msg = loop.run_until_complete(ensure_webhook())
        log.info("ensure_webhook: ok=%s\n%s", ok, msg)
        if ok:
            print(f"🚀 Admin bot is starting (webhook)…")
            run_webhook(app)
        else:
            log.warning("Webhook setup failed; falling back to POLLING")
            print(f"🚀 Admin bot is starting (polling)…")
            run_polling(app)
    else:
        print(f"🚀 Admin bot is starting (polling)…")
        run_polling(app)
