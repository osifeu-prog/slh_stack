# bot/run_admin_bot.py

import os, sys, json, logging, asyncio, time, re, traceback
from typing import List, Optional, Dict, Any
import httpx

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# =========================
# Env & defaults
# =========================

def _mask_token(tok: str) -> str:
    if not tok:
        return "(empty)"
    if len(tok) <= 12:
        return tok[:3] + "..." + tok[-3:]
    return tok[:6] + "..." + tok[-6:]

def _parse_port() -> int:
    """
    Railway/Platforms sometimes inject PORT or set BOT_PORT to '${PORT}'.
    Priority:
      1) BOT_PORT numeric
      2) PORT numeric
      3) 8081
    """
    raw = os.getenv("BOT_PORT", "").strip()
    if raw and raw.isdigit():
        return int(raw)
    # Try generic PORT
    raw2 = os.getenv("PORT", "").strip()
    if raw2.isdigit():
        return int(raw2)
    # Try forms like '${PORT}'
    if "PORT" in raw:
        raw3 = os.getenv("PORT", "").strip()
        if raw3.isdigit():
            return int(raw3)
    return 8081

TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
API     = os.getenv("SLH_API_BASE","http://127.0.0.1:8000").rstrip("/")
ADMINS  = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip().isdigit()]
MODE    = os.getenv("BOT_MODE","webhook").lower().strip()  # webhook | polling
PUBLIC  = os.getenv("BOT_WEBHOOK_PUBLIC_BASE","").rstrip("/")
PATH    = os.getenv("BOT_WEBHOOK_PATH","/tg")
SECRET  = os.getenv("BOT_WEBHOOK_SECRET","sela_secret_123")
PORT    = _parse_port()

DEFAULT_WALLET   = os.getenv("DEFAULT_WALLET","").strip()
DEFAULT_META_CID = os.getenv("DEFAULT_META_CID","").strip()
SELA_AMOUNT      = os.getenv("SELA_AMOUNT","0.15984").strip()

# =========================
# Basic validation
# =========================

if not TOKEN:
    print("TELEGRAM_BOT_TOKEN missing")
    sys.exit(1)

# Telegram restriction for secret token
if not re.fullmatch(r"[A-Za-z0-9_\-]+", SECRET):
    print("BOT_WEBHOOK_SECRET must contain only letters/digits/_/- (Telegram requirement)")
    sys.exit(1)

if MODE not in ("webhook", "polling"):
    print(f"BOT_MODE invalid: {MODE}. Use 'webhook' or 'polling'.")
    sys.exit(1)

# =========================
# Logging
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s"
)
log = logging.getLogger("slh.bot")

def _startup_banner():
    env_info = {
        "MODE": MODE,
        "API": API,
        "PUBLIC": PUBLIC or "(empty)",
        "PATH": PATH,
        "PORT": PORT,
        "SECRET(valid)": bool(re.fullmatch(r"[A-Za-z0-9_\-]+", SECRET)),
        "ADMINS": ADMINS or "(unset -> allow self)",
        "DEFAULT_WALLET": DEFAULT_WALLET or "(empty)",
        "DEFAULT_META_CID": DEFAULT_META_CID or "(empty)",
        "SELA_AMOUNT": SELA_AMOUNT,
        "TOKEN(masked)": _mask_token(TOKEN),
    }
    log.info("===== SLH Admin Bot – Startup =====")
    for k, v in env_info.items():
        log.info(f"{k}: {v}")

_startup_banner()

# =========================
# HTTP client helper
# =========================

async def api_post(path:str, payload:dict) -> Dict[str, Any]:
    url = f"{API}{path}"
    timeout = httpx.Timeout(25.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as cx:
        r = await cx.post(url, json=payload)
        r.raise_for_status()
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}

# Simple in-memory event log (ring buffer)
EVENTS: List[dict] = []
def push_event(ev:dict):
    ev = dict({"ts": int(time.time())}, **ev)
    EVENTS.append(ev)
    if len(EVENTS) > 500:
        del EVENTS[:200]

# =========================
# Admin logic / text blocks
# =========================

SUMMARY_MD = (
    "*SLH – Go-Live Pack (Testnet)*\n\n"
    "*0) Quick Ref*\n"
    "• Network: BSC Testnet (97)\n"
    "• NFT: `0x8AD1de67648dB44B1b1D0E3475485910CedDe90b`\n"
    "• Example CID: `QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq`\n"
)

def is_admin(user_id:int) -> bool:
    # If ADMINS unset, allow all (dev mode). In prod – set ADMIN_IDS!
    return (user_id in ADMINS) if ADMINS else True

# =========================
# Handlers
# =========================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    who = update.effective_user
    await update.message.reply_text(
        f"שלום {who.first_name or ''}! הבוט באוויר ✅  | נסה /ping או /adm_help"
    )

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Calls your API /healthz for a quick check."""
    try:
        timeout = httpx.Timeout(10.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as cx:
            r = await cx.get(f"{API}/healthz")
        await update.message.reply_text(r.text[:1000])
    except Exception as e:
        await update.message.reply_text(f"health error: {e}")

async def env_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    info = {
        "MODE": MODE,
        "API": API,
        "PUBLIC": PUBLIC or "(empty)",
        "PATH": PATH,
        "PORT": PORT,
        "SECRET(valid)": bool(re.fullmatch(r"[A-Za-z0-9_\-]+", SECRET)),
        "ADMINS": ADMINS or "(unset -> allow self)",
        "DEFAULT_WALLET": DEFAULT_WALLET or "(empty)",
        "DEFAULT_META_CID": DEFAULT_META_CID or "(empty)",
        "SELA_AMOUNT": SELA_AMOUNT,
        "TOKEN(masked)": _mask_token(TOKEN),
    }
    txt = "```\n" + json.dumps(info, indent=2, ensure_ascii=False) + "\n```"
    await update.message.reply_text(txt, parse_mode="Markdown")

async def adm_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    txt = (
        "*Admin commands:*\n"
        "/adm_sell `<wallet>` `<ipfs://CID|https://...>` `[note...]`\n"
        "/adm_testmint – mint+grant using defaults (for sanity)\n"
        "/adm_recent `[N]` – last events\n"
        "/adm_post_summary – post go-live card\n"
        "/health – call API /healthz\n"
        "/env – print bot env\n"
        "/ping – health check\n"
    )
    await update.message.reply_markdown(txt)

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
        await update.message.reply_text("No events yet.")
    else:
        await update.message.reply_text("```\n" + "\n\n".join(lines) + "\n```", parse_mode="Markdown")

async def adm_testmint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick sanity: uses DEFAULT_WALLET/DEFAULT_META_CID/SELA_AMOUNT."""
    if not is_admin(update.effective_user.id):
        return
    wallet = DEFAULT_WALLET
    cid = DEFAULT_META_CID
    if not wallet or not cid:
        await update.message.reply_text("Please set DEFAULT_WALLET and DEFAULT_META_CID in env.")
        return
    token_uri = f"ipfs://{cid}" if not cid.startswith("ipfs://") and not cid.startswith("http") else cid
    try:
        mint_res = await api_post("/v1/chain/mint-demo", {
            "to_wallet": wallet,
            "token_uri": token_uri
        })
        mint_tx = mint_res.get("tx") or mint_res.get("hash") or "-"

        grant_res = await api_post("/v1/chain/grant-sela", {
            "to_wallet": wallet,
            "amount": str(SELA_AMOUNT or "0.15984")
        })
        sela_tx = grant_res.get("tx") or grant_res.get("hash") or "-"

        push_event({
            "wallet": wallet,
            "token_uri": token_uri,
            "mint_tx": mint_tx,
            "sela_tx": sela_tx,
            "note": "adm_testmint"
        })

        msg = (
            "✅ *Test Mint + Grant*\n"
            f"• Wallet: `{wallet}`\n"
            f"• tokenURI: `{token_uri}`\n"
            f"• Mint TX: `{mint_tx}`\n"
            f"• SELA TX: `{sela_tx}`\n"
        )
        await update.message.reply_markdown(msg)
    except httpx.HTTPError as e:
        await update.message.reply_text(f"API HTTP error: {e}")
    except Exception as e:
        tb = traceback.format_exc(limit=2)
        await update.message.reply_text(f"Unexpected: {e}\n{tb}")

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
        grant_res = await api_post("/v1/chain/grant-sela", {
            "to_wallet": wallet,
            "amount": str(SELA_AMOUNT or "0.15984")
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
        await update.message.reply_text(f"API HTTP error: {e}")
    except Exception as e:
        tb = traceback.format_exc(limit=2)
        await update.message.reply_text(f"Unexpected: {e}\n{tb}")

async def echo_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text if update.message else ""
    if txt.startswith("/"):
        await update.message.reply_text("Unknown command. Try /adm_help")
    else:
        if update.effective_chat and str(update.effective_chat.type) == "ChatType.PRIVATE":
            await update.message.reply_text("Hi! Use /adm_help")

# =========================
# Application wiring
# =========================

def build_app():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ping",  ping_cmd))
    app.add_handler(CommandHandler("health", health_cmd))
    app.add_handler(CommandHandler("env", env_cmd))
    app.add_handler(CommandHandler("adm_help", adm_help))
    app.add_handler(CommandHandler("adm_post_summary", adm_post_summary))
    app.add_handler(CommandHandler("adm_recent", adm_recent))
    app.add_handler(CommandHandler("adm_testmint", adm_testmint))
    app.add_handler(CommandHandler("adm_sell", adm_sell))
    app.add_handler(MessageHandler(filters.ALL, echo_fallback))
    return app

def run_polling(app):
    log.info("Starting bot in POLLING mode…")
    app.run_polling(close_loop=False)

def run_webhook(app):
    # Telegram requires a FULL https URL for webhook
    if not PUBLIC.startswith("https://"):
        print("BOT_WEBHOOK_PUBLIC_BASE must be https for webhook mode")
        sys.exit(1)
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
        cert=None, key=None
    )

# =========================
# Main
# =========================

if __name__ == "__main__":
    print(f"🚀 Admin bot is starting ({MODE})…")
    app = build_app()
    try:
        if MODE == "polling":
            run_polling(app)
        else:
            run_webhook(app)
    except Exception as e:
        log.error("Fatal error on startup: %s", e)
        traceback.print_exc()
        sys.exit(1)
