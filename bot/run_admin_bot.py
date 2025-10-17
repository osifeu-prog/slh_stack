# bot/run_admin_bot.py
import os, sys, re, time, json, asyncio, logging, io, datetime
from typing import List, Tuple, Optional
import httpx

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =========================
# Environment & Constants
# =========================
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API     = os.getenv("SLH_API_BASE", "http://127.0.0.1:8000").rstrip("/")
MODE    = os.getenv("BOT_MODE", "webhook").lower().strip()          # webhook | polling
PUBLIC  = os.getenv("BOT_WEBHOOK_PUBLIC_BASE", "").rstrip("/")
PATH    = os.getenv("BOT_WEBHOOK_PATH", "/tg")
SECRET  = os.getenv("BOT_WEBHOOK_SECRET", "sela_secret_123")
PORT    = int((os.getenv("BOT_PORT") or os.getenv("PORT", "8080")).strip())

DEFAULT_WALLET   = os.getenv("DEFAULT_WALLET", "").strip()
DEFAULT_META_CID = os.getenv("DEFAULT_META_CID", "").strip()
SELA_AMOUNT      = os.getenv("SELA_AMOUNT", "0.15984").strip()
ADMIN_IDS_RAW    = os.getenv("ADMIN_IDS", "").strip()

# Parse admin list (digits only)
ADMINS: List[int] = []
if ADMIN_IDS_RAW:
    for piece in ADMIN_IDS_RAW.replace(" ", "").split(","):
        if piece.isdigit():
            ADMINS.append(int(piece))

# Secret token rules (Telegram restriction: only letters/digits/_/-)
if not re.fullmatch(r"[A-Za-z0-9_\-]+", SECRET):
    print("BOT_WEBHOOK_SECRET must contain only letters/digits/_/-")
    sys.exit(1)

if not TOKEN:
    print("TELEGRAM_BOT_TOKEN missing")
    sys.exit(1)

# BSC Testnet Explorer
BSC_EXPLORER = "https://testnet.bscscan.com"

# Where to store log exports in container
LOG_DIR = os.getenv("BOT_LOG_DIR", "/app/botdata/logs")

# =========================
# Logging
# =========================
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s"
)
log = logging.getLogger("slh.bot")

def mask_token(t: str) -> str:
    if len(t) <= 8:
        return "********"
    return f"{t[:6]}...{t[-6:]}"

# =========================
# Helpers
# =========================
def is_admin(user_id: Optional[int]) -> bool:
    """If ADMIN_IDS unset -> allow everyone (useful for dev); else enforce."""
    if user_id is None:
        return False
    return True if not ADMINS else (user_id in ADMINS)

def tx_link(tx_hash: str) -> str:
    tx = (tx_hash or "").strip()
    return f"{BSC_EXPLORER}/tx/{tx}" if tx and tx != "-" else "-"

async def api_post(path: str, payload: dict):
    """POST to our API with simple timeout & raise on HTTP errors."""
    url = f"{API}{path}"
    timeout = httpx.Timeout(25.0, connect=12.0)
    async with httpx.AsyncClient(timeout=timeout) as cx:
        r = await cx.post(url, json=payload)
        r.raise_for_status()
        return r.json()

# In-memory basic ring-buffer events
EVENTS: List[dict] = []
def push_event(ev: dict):
    ev = {"ts": int(time.time()), **ev}
    EVENTS.append(ev)
    if len(EVENTS) > 1000:
        del EVENTS[:400]

# Track last /start time (for “block” export)
LAST_START_TS = 0

# Quick summary card for admins/groups
SUMMARY_MD = (
    "*SLH – Go-Live Pack (Testnet)*\n\n"
    "*Quick Ref*\n"
    "• Network: BSC Testnet (97)\n"
    "• NFT: `0x8AD1de67648dB44B1b1D0E3475485910CedDe90b`\n"
    "• Example CID: `QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq`\n"
    f"• Default SELA amount: `{SELA_AMOUNT}`\n"
)

# Anti-spam memory for public /mint
_RECENT_MINTS = {}   # user_id -> ts

# =========================
# Keyboards
# =========================
def main_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("/mint"), KeyboardButton("/ping")],
        [KeyboardButton("/adm_help"), KeyboardButton("/adm_status")]
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# =========================
# User Handlers
# =========================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global LAST_START_TS
    LAST_START_TS = int(time.time())
    who = update.effective_user
    first = who.first_name if who and who.first_name else ""
    text = (
        f"שלום {first}! הבוט באוויר ✅\n"
        "שלב 1: ודאו שיש לכם BSC Testnet בארנק (MetaMask).\n"
        "שלב 2: שלחו /mint <כתובת־ארנק> כדי לקבל NFT + SELA.\n"
        "דוגמה: /mint 0x693db6c817083818696a7228aEbfBd0Cd3371f02\n"
        "לבדיקה מהירה: /ping  |  פקודות אדמין: /adm_help"
    )
    await update.message.reply_text(text, reply_markup=main_keyboard())
    push_event({"actor": f"user:{who.id if who else '-'}", "type": "start"})

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")

async def tx_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Utility: /tx <hash> -> returns explorer link."""
    args = context.args
    if not args:
        await update.message.reply_text("שימוש: /tx <hash>")
        return
    await update.message.reply_text(tx_link(args[0]))

async def mint_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Public mint:
      /mint 0xYourWallet
    Will: mint NFT with DEFAULT_META_CID + grant SELA.
    """
    user_id = update.effective_user.id if update.effective_user else 0
    now = int(time.time())
    last = _RECENT_MINTS.get(user_id, 0)
    if now - last < 15:  # soft anti-spam
        await update.message.reply_text("חכה רגע ונסה שוב…")
        return
    _RECENT_MINTS[user_id] = now

    args = context.args
    if not args:
        await update.message.reply_text("שימוש: /mint <WALLET>\nלדוגמה: /mint 0x693d...f02")
        return

    wallet = args[0].strip()
    token_uri = f"ipfs://{DEFAULT_META_CID}" if DEFAULT_META_CID else None
    if not token_uri:
        await update.message.reply_text("השרת לא הוגדר עם DEFAULT_META_CID.")
        return

    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet):
        await update.message.reply_text("הארנק לא נראה תקין (0x + 40 תווים הקס).")
        return

    try:
        # 1) Mint NFT
        mint_res = await api_post("/v1/chain/mint-demo", {
            "to_wallet": wallet,
            "token_uri": token_uri
        })
        mint_tx = mint_res.get("tx") or mint_res.get("hash") or "-"

        # 2) Grant SELA
        grant_res = await api_post("/v1/chain/grant-sela", {
            "to_wallet": wallet,
            "amount": str(SELA_AMOUNT)
        })
        sela_tx = grant_res.get("tx") or grant_res.get("hash") or "-"

        push_event({
            "actor": f"user:{user_id}",
            "type": "mint_public",
            "wallet": wallet,
            "token_uri": token_uri,
            "mint_tx": mint_tx,
            "sela_tx": sela_tx,
        })

        msg = (
            "🎉 *Mint + SELA Granted!*\n"
            f"• Wallet: `{wallet}`\n"
            f"• tokenURI: `{token_uri}`\n"
            f"• Mint TX: `{mint_tx}`\n"
            f"  ↪️ {tx_link(mint_tx)}\n"
            f"• SELA TX: `{sela_tx}`\n"
            f"  ↪️ {tx_link(sela_tx)}\n"
        )
        await update.message.reply_markdown(msg)
    except httpx.HTTPError as e:
        await update.message.reply_text(f"API error: {e}")
    except Exception as e:
        await update.message.reply_text(f"Unexpected: {e}")

# =========================
# Admin: help/status/webhook/recent/export
# =========================
async def adm_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    txt = (
        "פקודות אדמין:\n"
        "• /adm_status — מצב ריצה והגדרות\n"
        "• /adm_setwebhook — קובע webhook לפי ההגדרות הנוכחיות\n"
        "• /adm_recent [N] — מציג אחרונים וגם *שומר בלוק לוג* מאז /start האחרון\n"
        "• /adm_export — מייצא בלוק לוג מאז /start האחרון (כקובץ)\n"
        "• /adm_sell — אשף שלבי מכירה (wallet → tokenURI → note → אימות)\n"
        "• /adm_echo <טקסט> — החזר טקסט (בדיקה)\n"
        "• /tx <hash> — קישור מהיר ל־BscScan\n"
        "• /mint <wallet> — (ציבורי) הנפקת NFT + SELA\n"
    )
    await update.message.reply_text(txt, reply_markup=main_keyboard())

async def adm_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    status = (
        "Status:\n\n"
        f"MODE={MODE} | PORT={PORT} | PUBLIC='{PUBLIC}' | PATH='{PATH}' | SECRET.len={len(SECRET)} | API='{API}'\n"
        f"DEFAULT_WALLET={DEFAULT_WALLET or '-'} | DEFAULT_META_CID={DEFAULT_META_CID or '-'} | SELA_AMOUNT={SELA_AMOUNT}\n"
        f"ADMINS={','.join(map(str, ADMINS)) if ADMINS else '(unset -> allow self)'}"
    )
    await update.message.reply_text(status)

async def adm_setwebhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    ok, msg = await ensure_webhook()
    await update.message.reply_text(f"SetWebhook → {ok}\n{msg}")

def _events_since_last_start() -> List[dict]:
    if LAST_START_TS <= 0:
        return EVENTS[-50:]  # fallback
    return [ev for ev in EVENTS if ev.get("ts", 0) >= LAST_START_TS]

def _format_events(lines: List[dict]) -> str:
    out = []
    for ev in lines:
        dt = datetime.datetime.utcfromtimestamp(ev["ts"]).isoformat() + "Z"
        out.append(
            f"[{dt}] actor={ev.get('actor','-')} type={ev.get('type','-')}\n"
            f"wallet={ev.get('wallet','-')} tokenURI={ev.get('token_uri','-')}\n"
            f"mint={ev.get('mint_tx','-')} sela={ev.get('sela_tx','-')}\n"
        )
    return "\n".join(out) if out else "(no events in block)"

def _save_log_block(prefix: str, body: str) -> str:
    ts = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(LOG_DIR, f"{prefix}-{ts}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path

async def adm_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    n = 20
    if context.args and context.args[0].isdigit():
        n = min(int(context.args[0]), 100)

    # show last N
    tail = EVENTS[-n:]
    txt_list = []
    for ev in tail:
        txt_list.append(
            f"ts={ev.get('ts')} | by={ev.get('actor','-')} | type={ev.get('type','-')} | wallet={ev.get('wallet','-')}\n"
            f"tokenURI={ev.get('token_uri','-')} | mint={ev.get('mint_tx','-')} | sela={ev.get('sela_tx','-')}"
        )
    await update.message.reply_text("No events yet." if not txt_list else "```\n" + "\n\n".join(txt_list) + "\n```", parse_mode="Markdown")

    # also save “block since /start” and send as file
    block = _format_events(_events_since_last_start())
    path = _save_log_block("events-block", block)
    with open(path, "rb") as fh:
        await update.message.reply_document(InputFile(fh, filename=os.path.basename(path)), caption="Events block saved (since last /start)")

async def adm_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    block = _format_events(_events_since_last_start())
    path = _save_log_block("events-block", block)
    with open(path, "rb") as fh:
        await update.message.reply_document(InputFile(fh, filename=os.path.basename(path)), caption="Exported events block (since last /start)")

async def adm_echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = " ".join(context.args) if context.args else "(no text)"
    await update.message.reply_text(f"echo: {text}")

# =========================
# Admin: SELL Wizard (Conversation)
# =========================
SELL_WALLET, SELL_URI, SELL_NOTE, SELL_CONFIRM = range(4)

def _sell_intro() -> str:
    return (
        "אשף /adm_sell – נבצע מכירה ידנית בשלבים:\n"
        "1) ארנק יעד (0x…40 hex)\n"
        "2) tokenURI – אפשר `ipfs://CID` או רק CID (נתרגם), או URL מלא\n"
        "3) הערה (אופציונלי)\n"
        "בסוף תקבלו תקציר ונתבקש לאשר ✅"
    )

async def adm_sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(_sell_intro() + "\n\nשלב 1/3 – הכניסו WALLET:")
    return SELL_WALLET

async def adm_sell_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    w = (update.message.text or "").strip()
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", w):
        await update.message.reply_text("הארנק לא נראה תקין. נסו שוב (0x + 40 הקס).")
        return SELL_WALLET
    context.user_data["sell_wallet"] = w
    await update.message.reply_text("שלב 2/3 – הכניסו tokenURI:\n"
                                    "• `ipfs://<CID>` או רק `<CID>` (אוסיף ipfs://)\n"
                                    "• או לינק https מלא")
    return SELL_URI

async def adm_sell_uri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = (update.message.text or "").strip()
    if u.startswith("ipfs://"):
        token_uri = u
    elif re.match(r"^Qm[1-9A-Za-z]{44,}", u):
        token_uri = f"ipfs://{u}"
    else:
        token_uri = u  # accept https
    context.user_data["sell_token_uri"] = token_uri
    await update.message.reply_text("שלב 3/3 – כתבו הערה (או /skip):")
    return SELL_NOTE

async def adm_sell_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sell_note"] = (update.message.text or "").strip()
    return await _adm_sell_confirm(update, context)

async def adm_sell_skip_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["sell_note"] = ""
    return await _adm_sell_confirm(update, context)

async def _adm_sell_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    w = context.user_data.get("sell_wallet", "-")
    t = context.user_data.get("sell_token_uri", "-")
    n = context.user_data.get("sell_note", "")
    echo = (
        "אישור נתונים:\n"
        f"• Wallet: `{w}`\n"
        f"• tokenURI: `{t}`\n"
        f"• Note: `{n or '(none)'}`\n\n"
        "להמשך הקלידו: `confirm`\nלביטול: `cancel`"
    )
    await update.message.reply_markdown(echo)
    return SELL_CONFIRM

async def adm_sell_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip().lower()
    if txt not in ("confirm", "cancel"):
        await update.message.reply_text("הקלידו `confirm` להמשך או `cancel` לביטול.")
        return SELL_CONFIRM
    if txt == "cancel":
        await update.message.reply_text("בוטל.")
        return ConversationHandler.END

    # run the sell
    wallet = context.user_data.get("sell_wallet", "")
    token_uri = context.user_data.get("sell_token_uri", "")
    note = context.user_data.get("sell_note", "")

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
            "actor": f"admin:{update.effective_user.id}",
            "type": "sell_manual",
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
            f"  ↪️ {tx_link(mint_tx)}\n"
            f"• SELA TX: `{sela_tx}`\n"
            f"  ↪️ {tx_link(sela_tx)}\n"
        )
        await update.message.reply_markdown(msg)
    except httpx.HTTPError as e:
        await update.message.reply_text(f"API error: {e}")
    except Exception as e:
        await update.message.reply_text(f"Unexpected: {e}")

    return ConversationHandler.END

async def adm_sell_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("בוטל.")
    return ConversationHandler.END

# =========================
# Fallback & Error Logging
# =========================
async def echo_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch-all: log every update & guide users in private chat."""
    try:
        uid = update.effective_user.id if update.effective_user else "-"
        cid = update.effective_chat.id if update.effective_chat else "-"
        txt = update.message.text if update.message else ""
        log.info(f"[UPDATE] chat={cid} user={uid} text={txt}")
    except Exception:
        pass

    if update.message and update.message.text and update.message.text.startswith("/"):
        await update.message.reply_text("Unknown command. Try /mint או /adm_help")
    else:
        if update.effective_chat and str(update.effective_chat.type) == "ChatType.PRIVATE":
            await update.message.reply_text("היי! כתוב /mint <wallet> להנפקה, או /adm_help")

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Handler error", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("⚠️ שגיאה בלתי צפויה. נסו שוב.")
    except Exception:
        pass

# =========================
# Webhook bootstrap
# =========================
async def ensure_webhook() -> Tuple[bool, str]:
    """
    Sets Telegram webhook via raw HTTP BEFORE starting app.run_webhook.
    Good for health-check & predictable startup.
    """
    if not PUBLIC.startswith("https://"):
        return False, "PUBLIC base must be https"
    url = PUBLIC + PATH
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=10)) as cx:
            del_res = (await cx.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")).json()
            set_res = (await cx.post(
                f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                data={"url": url, "secret_token": SECRET}
            )).json()
            info_res = (await cx.get(f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")).json()
        log.info("ensure_webhook: ok=True")
        log.info(f"url={url}")
        log.info(f"delete={del_res}")
        log.info(f"set={set_res}")
        log.info(f"info={info_res}")
        return True, url
    except Exception as e:
        return False, f"ensure_webhook error: {e}"

# =========================
# App Builder & Runners
# =========================
def build_app():
    app = ApplicationBuilder().token(TOKEN).build()

    # User commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ping",  ping_cmd))
    app.add_handler(CommandHandler("mint",  mint_cmd))
    app.add_handler(CommandHandler("tx",    tx_cmd))

    # Admin simple commands
    app.add_handler(CommandHandler("adm_help",       adm_help))
    app.add_handler(CommandHandler("adm_status",     adm_status))
    app.add_handler(CommandHandler("adm_setwebhook", adm_setwebhook))
    app.add_handler(CommandHandler("adm_recent",     adm_recent))
    app.add_handler(CommandHandler("adm_export",     adm_export))
    app.add_handler(CommandHandler("adm_echo",       adm_echo))

    # Admin SELL wizard (Conversation)
    sell_conv = ConversationHandler(
        entry_points=[CommandHandler("adm_sell", adm_sell_start)],
        states={
            SELL_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_sell_wallet)],
            SELL_URI:    [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_sell_uri)],
            SELL_NOTE:   [
                CommandHandler("skip", adm_sell_skip_note),
                MessageHandler(filters.TEXT & ~filters.COMMAND, adm_sell_note),
            ],
            SELL_CONFIRM:[MessageHandler(filters.TEXT & ~filters.COMMAND, adm_sell_do)],
        },
        fallbacks=[CommandHandler("cancel", adm_sell_cancel)],
        name="sell_conv",
        persistent=False,
    )
    app.add_handler(sell_conv)

    # Fallback + error logging
    app.add_handler(MessageHandler(filters.ALL, echo_fallback))
    app.add_error_handler(on_error)
    return app

def run_polling(app):
    log.info("Starting bot in POLLING mode…")
    app.run_polling(close_loop=False)

def run_webhook(app):
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
    log.info("===== SLH Admin Bot – Startup =====")
    log.info(f"MODE: {MODE}")
    log.info(f"API: {API}")
    log.info(f"PUBLIC: {PUBLIC}")
    log.info(f"PATH: {PATH}")
    log.info(f"PORT: {PORT}")
    log.info(f"SECRET(valid): {bool(re.fullmatch(r'[A-Za-z0-9_\\-]+', SECRET))}")
    log.info(f"ADMINS: {','.join(map(str, ADMINS)) if ADMINS else '(unset -> allow self)'}")
    log.info(f"DEFAULT_WALLET: {DEFAULT_WALLET or '-'}")
    log.info(f"DEFAULT_META_CID: {DEFAULT_META_CID or '-'}")
    log.info(f"SELA_AMOUNT: {SELA_AMOUNT}")
    log.info(f"TOKEN(masked): {mask_token(TOKEN)}")
    log.info(f"LOG_DIR: {LOG_DIR}")

    # Ensure webhook before Application takes over (webhook mode)
    if MODE == "webhook":
        ok, msg = asyncio.run(ensure_webhook())
        if not ok:
            log.error(f"ensure_webhook FAILED: {msg}")

    print(f"🚀 Admin bot is starting ({MODE})…")
    app = build_app()

    # Run it
    if MODE == "polling":
        run_polling(app)
    else:
        run_webhook(app)

"""
=========================
ENV you should set (Railway)
=========================
# BOT (bot service)
TELEGRAM_BOT_TOKEN=82250...   # from @BotFather
SLH_API_BASE=https://slhstack-production.up.railway.app
BOT_MODE=webhook
BOT_PORT=8080
BOT_WEBHOOK_PUBLIC_BASE=https://slhbot-bot.up.railway.app
BOT_WEBHOOK_PATH=/tg
BOT_WEBHOOK_SECRET=sela_secret_123             # only letters/digits/_/-
# optional:
ADMIN_IDS=224223270

# API (api service)
BSC_RPC_URL=https://bsc-testnet-rpc.publicnode.com
NFT_CONTRACT=0x8AD1de67648dB44B1b1D0E3475485910CedDe90b
CHAIN_ID=97
TREASURY_PRIVATE_KEY=0x...     # test-wallet private key with a bit of test BNB
DEFAULT_WALLET=0x693db6c817083818696a7228aEbfBd0Cd3371f02
DEFAULT_META_CID=QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq
SELA_AMOUNT=0.15984
"""
