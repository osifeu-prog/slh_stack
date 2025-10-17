\
import os, sys, re, time, json, logging, asyncio, warnings
from typing import List
import httpx

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

warnings.filterwarnings("ignore", category=DeprecationWarning)

TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
API     = os.getenv("SLH_API_BASE","http://127.0.0.1:8080").rstrip("/")
ADMINS  = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip().isdigit()]
MODE    = os.getenv("BOT_MODE","webhook").lower().strip()
PUBLIC  = os.getenv("BOT_WEBHOOK_PUBLIC_BASE","").rstrip("/")
PATH    = os.getenv("BOT_WEBHOOK_PATH","/tg")
SECRET  = os.getenv("BOT_WEBHOOK_SECRET","sela_secret_123")
PORT    = int(os.getenv("BOT_PORT", os.getenv("PORT","8080")))

DEFAULT_WALLET   = os.getenv("DEFAULT_WALLET","").strip()
DEFAULT_META_CID = os.getenv("DEFAULT_META_CID","").strip()
SELA_AMOUNT      = os.getenv("SELA_AMOUNT","0.15984").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
log = logging.getLogger("slh.bot")

def mask_token(t: str) -> str:
    if len(t) < 8: return "***"
    return f"{t[:6]}...{t[-6:]}"

def secret_ok(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_\\-]+", s or ""))

log.info("===== SLH Admin Bot – Startup =====")
log.info(f"MODE: {MODE}")
log.info(f"API: {API}")
log.info(f"PUBLIC: {PUBLIC}")
log.info(f"PATH: {PATH}")
log.info(f"PORT: {PORT}")
log.info(f"SECRET(valid): {secret_ok(SECRET)}")
log.info(f"ADMINS: {'(unset -> allow self)'}" if not ADMINS else f"{ADMINS}")
log.info(f"DEFAULT_WALLET: {DEFAULT_WALLET or '-'}")
log.info(f"DEFAULT_META_CID: {DEFAULT_META_CID or '-'}")
log.info(f"SELA_AMOUNT: {SELA_AMOUNT}")
log.info(f"TOKEN(masked): {mask_token(TOKEN)}")

if not TOKEN:
    print("TELEGRAM_BOT_TOKEN missing"); sys.exit(1)
if MODE == "webhook" and not PUBLIC.startswith("https://"):
    print("BOT_WEBHOOK_PUBLIC_BASE must be https for webhook mode"); sys.exit(1)
if MODE == "webhook" and not secret_ok(SECRET):
    print("BOT_WEBHOOK_SECRET must contain only letters/digits/_/-"); sys.exit(1)

def is_admin(user_id:int) -> bool:
    return (user_id in ADMINS) if ADMINS else True

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
    "*SLH – Go-Live Pack (Testnet)*\\n\\n"
    "*0) Quick Ref*\\n"
    "• Network: BSC Testnet (97)\\n"
    "• NFT: `0x8AD1de67648dB44B1b1D0E3475485910CedDe90b`\\n"
    "• Example CID: `QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq`\\n"
)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    who = update.effective_user
    await update.message.reply_text(
        f"שלום {who.first_name or ''}! הבוט באוויר ✅\\nנסה /ping או /adm_help"
    )

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")

async def adm_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    txt = (
        "פקודות אדמין שימושיות:\\n"
        "/adm_status — מצב ריצה והגדרות\\n"
        "/adm_setwebhook — קובע webhook לפי ההגדרות הנוכחיות\\n"
        "/adm_echo <טקסט> — החזר טקסט (בדיקה)\\n"
        "/adm_recent [N] — אחרונים ללוג\\n"
        "/adm_sell <wallet> <ipfs://CID|https://...> [note] — מכירה ידנית מלאה\\n"
        "/ping — בדיקת חיים\\n"
    )
    await update.message.reply_text(txt)

async def adm_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    msg = (
        f"Status:\\n"
        f"MODE={MODE} | PORT={PORT} | PUBLIC='{PUBLIC}' | PATH='{PATH}' | SECRET.len={len(SECRET)} | API='{API}'"
    )
    await update.message.reply_text(msg)

async def adm_setwebhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    ok, details = await ensure_webhook()
    txt = f"SetWebhook → {ok}\\n{details.get('url','')}"
    await update.message.reply_text(txt)

async def adm_echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    text = " ".join(context.args) if context.args else "(no text)"
    await update.message.reply_text(f"echo: {text}")

async def adm_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    n = 20
    if context.args and context.args[0].isdigit():
        n = min(int(context.args[0]), 100)
    lines = []
    for ev in EVENTS[-n:]:
        lines.append(
            f"ts={ev.get('ts')} | wallet={ev.get('wallet','-')} | tokenURI={ev.get('token_uri','-')}\\n"
            f"mint={ev.get('mint_tx','-')} | sela={ev.get('sela_tx','-')} | note={ev.get('note','-')}"
        )
    if not lines:
        await update.message.reply_text("No events yet.")
    else:
        await update.message.reply_text("```\\n" + "\\n\\n".join(lines) + "\\n```", parse_mode="Markdown")

async def adm_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
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
            "✅ *Sold + Granted*\\n"
            f"• Wallet: `{wallet}`\\n"
            f"• tokenURI: `{token_uri}`\\n"
            f"• Mint TX: `{mint_tx}`\\n"
            f"• SELA TX: `{sela_tx}`\\n"
        )
        await update.message.reply_markdown(msg)

    except httpx.HTTPError as e:
        await update.message.reply_text(f"API error: {e}")
    except Exception as e:
        await update.message.reply_text(f"Unexpected: {e}")

async def echo_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text if update.message else ""
    if txt.startswith("/"):
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
    app.add_handler(CommandHandler("adm_recent", adm_recent))
    app.add_handler(CommandHandler("adm_sell", adm_sell))
    app.add_handler(CommandHandler("adm_echo", adm_echo))
    app.add_handler(MessageHandler(filters.ALL, echo_fallback))
    return app

async def ensure_webhook():
    url = PUBLIC + PATH
    async with httpx.AsyncClient(timeout=10.0) as cx:
        r1 = await cx.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")
        r2 = await cx.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                           json={"url": url, "secret_token": SECRET})
        r3 = await cx.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")
    return True, {"url": url, "delete": r1.json(), "set": r2.json(), "info": r3.json()}

def run_polling(app):
    log.info("Starting bot in POLLING mode…")
    app.run_polling(close_loop=False)

def run_webhook(app):
    url = PUBLIC + PATH
    log.info(f"Starting bot in WEBHOOK mode at {url} (port {PORT})")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=url,
        secret_token=SECRET,
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False,
    )

if __name__ == "__main__":
    try:
        ok, msg = asyncio.get_event_loop().run_until_complete(ensure_webhook())
        log.info(f"ensure_webhook: ok={ok}")
        log.info(f"url={msg.get('url')}")
        log.info(f"delete={msg.get('delete')}")
        log.info(f"set={msg.get('set')}")
        log.info(f"info={msg.get('info')}")
    except Exception as e:
        log.warning(f"ensure_webhook failed: {e}")

    print(f"🚀 Admin bot is starting ({MODE})…")
    app = build_app()
    if MODE == "polling":
        run_polling(app)
    else:
        run_webhook(app)
