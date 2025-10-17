# -*- coding: utf-8 -*-
import os, sys, json, logging, asyncio, time, re, pathlib, io
from typing import List, Dict, Tuple, Optional
import httpx

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# Environment & Defaults
# =========================
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
API     = os.getenv("SLH_API_BASE","http://127.0.0.1:8000").rstrip("/")
MODE    = os.getenv("BOT_MODE","webhook").lower().strip()  # webhook | polling
PUBLIC  = os.getenv("BOT_WEBHOOK_PUBLIC_BASE","").rstrip("/")
PATH    = os.getenv("BOT_WEBHOOK_PATH","/tg")
SECRET  = os.getenv("BOT_WEBHOOK_SECRET","sela_secret_123")
PORT    = int(os.getenv("BOT_PORT", os.getenv("PORT","8080")))
ADMINS  = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip().isdigit()]

DEFAULT_WALLET   = os.getenv("DEFAULT_WALLET","").strip()
DEFAULT_META_CID = os.getenv("DEFAULT_META_CID","").strip()  # e.g. Qm....
SELA_AMOUNT      = os.getenv("SELA_AMOUNT","0.15984").strip()

LOG_DIR          = os.getenv("BOT_LOG_DIR", "/app/botdata/logs").strip()

if not TOKEN:
    print("TELEGRAM_BOT_TOKEN missing"); sys.exit(1)

# Telegram restriction for secret token (letters/digits/_/- only)
if not re.fullmatch(r"[A-Za-z0-9_\-]+", SECRET):
    print("BOT_WEBHOOK_SECRET must contain only letters/digits/_/-")
    sys.exit(1)

# =========================
# Logging
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s"
)
log = logging.getLogger("slh.bot")

# Create log dir
try:
    pathlib.Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
except Exception as e:
    log.error(f"Failed creating LOG_DIR={LOG_DIR}: {e}")

RUN_TS = int(time.time())
RUN_ID = time.strftime("%Y%m%d-%H%M%S", time.gmtime(RUN_TS))
SESSION_LOG_FILE = os.path.join(LOG_DIR, f"session-{RUN_ID}.log")

def write_log_line(line: str):
    try:
        with open(SESSION_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line.rstrip() + "\n")
    except Exception as e:
        log.error(f"write_log_line failed: {e}")

# =========================
# Helpers: Admin, API calls
# =========================
def is_admin(user_id: int) -> bool:
    # אם לא הוגדרו אדמינים — נניח מצב פיתוח (לא מומלץ בפרודקשן)
    return (user_id in ADMINS) if ADMINS else True

def _mask_token(t: str) -> str:
    if len(t) < 8:
        return "****"
    return f"{t[:6]}...{t[-6:]}"

async def api_get(path: str, params: dict | None = None):
    url = f"{API}{path}"
    timeout = httpx.Timeout(20, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as cx:
        r = await cx.get(url, params=params)
        r.raise_for_status()
        return r.json()

async def api_post(path: str, payload: dict):
    url = f"{API}{path}"
    timeout = httpx.Timeout(30, connect=12)
    async with httpx.AsyncClient(timeout=timeout) as cx:
        r = await cx.post(url, json=payload)
        r.raise_for_status()
        return r.json()

# =========================
# In-memory events + file
# =========================
EVENTS: List[dict] = []

def push_event(ev: dict):
    ev = dict({"ts": int(time.time())}, **ev)
    EVENTS.append(ev)
    if len(EVENTS) > 800:
        del EVENTS[:300]
    # write to file (append)
    write_log_line(json.dumps(ev, ensure_ascii=False))

def block_header(title: str) -> str:
    return f"===== {title} | {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ====="

# =========================
# On-boot summary for admins
# =========================
def startup_dump():
    lines = [
        "===== SLH Admin Bot – Startup =====",
        f"MODE: {MODE}",
        f"API: {API}",
        f"PUBLIC: {PUBLIC}",
        f"PATH: {PATH}",
        f"PORT: {PORT}",
        f"SECRET(valid): {bool(re.fullmatch(r'[A-Za-z0-9_\\-]+', SECRET))}",
        f"ADMINS: {'|'.join(map(str, ADMINS)) if ADMINS else '(unset -> allow self)'}",
        f"DEFAULT_WALLET: {DEFAULT_WALLET or '-'}",
        f"DEFAULT_META_CID: {DEFAULT_META_CID or '-'}",
        f"SELA_AMOUNT: {SELA_AMOUNT}",
        f"TOKEN(masked): {_mask_token(TOKEN)}",
        f"LOG_DIR: {LOG_DIR}",
    ]
    for ln in lines: log.info(ln)
    write_log_line("\n".join(lines))

# =========================
# Webhook ensure (+ tools)
# =========================
async def ensure_webhook() -> Tuple[bool, str]:
    """Delete + set webhook, then fetch getWebhookInfo and summarize."""
    if not PUBLIC.startswith("https://"):
        return False, "BOT_WEBHOOK_PUBLIC_BASE must be https for webhook mode"
    url = PUBLIC + PATH
    try:
        async with httpx.AsyncClient(timeout=20) as cx:
            delete = (await cx.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook")).json()
            set_    = (await cx.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                                     data={"url": url, "secret_token": SECRET})).json()
            info    = (await cx.get (f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo")).json()
        log.info("ensure_webhook: ok=True")
        log.info(f"url={url}")
        log.info(f"delete={delete}")
        log.info(f"set={set_}")
        log.info(f"info={info}")
        write_log_line(block_header("ensure_webhook"))
        write_log_line(json.dumps({"url": url, "delete": delete, "set": set_, "info": info}, ensure_ascii=False))
        return True, "ok"
    except Exception as e:
        log.error(f"ensure_webhook failed: {e}")
        return False, str(e)

def _ensure_main_loop():
    """
    Python 3.12 + PTB 20.8: לעיתים אין event loop ב־MainThread.
    ניצור אחד כדי למנוע RuntimeError.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

# =========================
# Guided state for /adm_sell wizard
# =========================
WIZ_SELL: Dict[int, Dict[str, str]] = {}

def reset_wiz(user_id: int):
    if user_id in WIZ_SELL:
        del WIZ_SELL[user_id]

# =========================
# Handlers
# =========================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    who = update.effective_user
    msg = (
        f"שלום {who.first_name or ''}! הבוט באוויר ✅\n"
        "נסה /ping או /adm_help\n\n"
        "למשתתפים:\n"
        f"שלחו: `/mint <כתובת־ארנק>` כדי לקבל NFT (CID ברירת מחדל) + SELA {SELA_AMOUNT}\n"
        "דוגמה:\n"
        "`/mint 0x1234...abcd`\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")

async def health_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """בדיקת בריאות נגד ה-API /healthz + סיכום קצר."""
    try:
        h = await api_get("/healthz")
        ok = h.get("ok")
        net = h.get("network","?")
        contract = h.get("contract","?")
        await update.message.reply_text(
            f"healthz: ok={ok} | network={net} | contract={contract}"
        )
    except Exception as e:
        await update.message.reply_text(f"healthz error: {e}")

async def adm_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    txt = (
        "*פקודות אדמין שימושיות:*\n"
        "/adm_status — מצב ריצה והגדרות\n"
        "/adm_setwebhook — קובע webhook לפי ההגדרות הנוכחיות\n"
        "/adm_recent [N] — האירועים האחרונים | אפשר גם `save` לשמירה לקובץ\n"
        "/adm_sell `<wallet> <ipfs://CID|https://...> [note]` — מהיר\n"
        "/adm_sell — ללא פרמטרים: אשף דו־שלבי + אישור\n"
        "/adm_echo <טקסט> — החזר טקסט (בדיקה)\n"
        "/ping — בדיקת חיים\n"
        "/health — בדיקת /healthz של ה־API\n"
    )
    await update.message.reply_markdown(txt)

async def adm_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    info = (
        "Status:\n\n"
        f"MODE={MODE} | PORT={PORT} | PUBLIC='{PUBLIC}' | PATH='{PATH}' | SECRET.len={len(SECRET)} | API='{API}'\n"
        f"DEFAULT_WALLET={DEFAULT_WALLET or '-'} | DEFAULT_META_CID={DEFAULT_META_CID or '-'} | SELA_AMOUNT={SELA_AMOUNT}\n"
        f"LOG_DIR={LOG_DIR}\n"
        f"SESSION_LOG={os.path.basename(SESSION_LOG_FILE)}"
    )
    await update.message.reply_text(info)

async def adm_setwebhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    ok, msg = await ensure_webhook()
    await update.message.reply_text(f"SetWebhook → {ok}\n{PUBLIC}{PATH}")

async def adm_echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = " ".join(context.args) if context.args else "(no text)"
    await update.message.reply_text(f"echo: {text}")

async def adm_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    # special: /adm_recent save → force save block file
    if context.args and context.args[0].lower() == "save":
        # פשוט מצביע על קובץ הסשן הנוכחי
        await update.message.reply_text(f"Saved to file: {os.path.basename(SESSION_LOG_FILE)}")
        return

    n = 20
    if context.args and context.args[0].isdigit():
        n = min(int(context.args[0]), 120)
    if not EVENTS:
        await update.message.reply_text("No events yet.")
        return
    lines = [block_header(f"RECENT last {n}")]
    for ev in EVENTS[-n:]:
        lines.append(
            f"ts={ev.get('ts')} | type={ev.get('type','-')} | wallet={ev.get('wallet','-')}\n"
            f"tokenURI={ev.get('token_uri','-')} | mint={ev.get('mint_tx','-')} | sela={ev.get('sela_tx','-')} | note={ev.get('note','-')}"
        )
    txt = "```\n" + ("\n\n".join(lines)) + "\n```"
    await update.message.reply_text(txt, parse_mode=ParseMode.MARKDOWN)

# ---------- /mint (לכל המשתמשים) ----------
async def mint_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User-facing mint: /mint <wallet> — uses DEFAULT_META_CID for token_uri, then grant SELA."""
    if not context.args:
        await update.message.reply_markdown(
            "שימוש: `/mint <כתובת־ארנק>`\nדוגמה: `/mint 0x1234...abcd`"
        )
        return

    wallet = context.args[0].strip()
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet):
        await update.message.reply_text("כתובת ארנק לא תקינה (צורה: 0x… 40 hex).")
        return

    if not DEFAULT_META_CID:
        await update.message.reply_text("Default CID לא מוגדר בשרת (DEFAULT_META_CID). פנה לאדמין.")
        return

    token_uri = f"ipfs://{DEFAULT_META_CID}"
    try:
        # Mint
        mint_res = await api_post("/v1/chain/mint-demo", {
            "to_wallet": wallet,
            "token_uri": token_uri
        })
        mint_tx = mint_res.get("tx") or mint_res.get("hash") or "-"

        # Grant SELA
        grant_res = await api_post("/v1/chain/grant-sela", {
            "to_wallet": wallet,
            "amount": str(SELA_AMOUNT)
        })
        sela_tx = grant_res.get("tx") or grant_res.get("hash") or "-"

        push_event({
            "type": "mint_user",
            "wallet": wallet,
            "token_uri": token_uri,
            "mint_tx": mint_tx,
            "sela_tx": sela_tx,
            "note": "user /mint"
        })

        links = []
        if re.fullmatch(r"0x[0-9a-fA-F]{64}", mint_tx):
            links.append(f"[Mint TX](https://testnet.bscscan.com/tx/{mint_tx})")
        if re.fullmatch(r"0x[0-9a-fA-F]{64}", sela_tx):
            links.append(f"[SELA TX](https://testnet.bscscan.com/tx/{sela_tx})")
        links_str = " | ".join(links) if links else "(לינקים יופיעו לאחר כרייה)"

        msg = (
            "✅ *הונפק לך NFT והועבר SELA!*\n"
            f"• Wallet: `{wallet}`\n"
            f"• tokenURI: `{token_uri}`\n"
            f"• {links_str}\n"
        )
        await update.message.reply_markdown(msg, disable_web_page_preview=True)

    except httpx.HTTPError as e:
        await update.message.reply_text(f"API error: {e}")
    except Exception as e:
        await update.message.reply_text(f"Unexpected: {e}")

# ---------- /adm_sell (מהיר או אשף) ----------
async def adm_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    uid = update.effective_user.id

    # מצב מהיר עם ארגומנטים
    if len(context.args) >= 2:
        wallet = context.args[0].strip()
        uri_in  = context.args[1].strip()
        note    = " ".join(context.args[2:]).strip() if len(context.args) > 2 else ""
        await _exec_sell(update, wallet, uri_in, note)
        return

    # אשף דו-שלבי
    WIZ_SELL[uid] = {"step": "wallet"}
    await update.message.reply_text(
        "אשף הנפקה למכירה 🚀\n"
        "שלב 1/2 — שלח/י את כתובת הארנק (0x…):"
    )

async def _exec_sell(update: Update, wallet: str, uri_in: str, note: str):
    # Normalize token_uri
    if uri_in.startswith("ipfs://"):
        token_uri = uri_in
    elif re.match(r"^Qm[1-9A-Za-z]{44,}", uri_in):
        token_uri = f"ipfs://{uri_in}"
    else:
        token_uri = uri_in  # allow https

    # Validate wallet
    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", wallet):
        await update.message.reply_text("כתובת ארנק לא תקינה (צורה: 0x… 40 hex).")
        return

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
            "type": "adm_sell",
            "wallet": wallet,
            "token_uri": token_uri,
            "mint_tx": mint_tx,
            "sela_tx": sela_tx,
            "note": note
        })

        links = []
        if re.fullmatch(r"0x[0-9a-fA-F]{64}", mint_tx):
            links.append(f"[Mint TX](https://testnet.bscscan.com/tx/{mint_tx})")
        if re.fullmatch(r"0x[0-9a-fA-F]{64}", sela_tx):
            links.append(f"[SELA TX](https://testnet.bscscan.com/tx/{sela_tx})")
        links_str = " | ".join(links) if links else "(לינקים יופיעו לאחר כרייה)"

        msg = (
            "✅ *Sold + Granted*\n"
            f"• Wallet: `{wallet}`\n"
            f"• tokenURI: `{token_uri}`\n"
            f"• {links_str}\n"
        )
        await update.message.reply_markdown(msg, disable_web_page_preview=True)

    except httpx.HTTPError as e:
        await update.message.reply_text(f"API error: {e}")
    except Exception as e:
        await update.message.reply_text(f"Unexpected: {e}")

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Router לפלואו אשף /adm_sell + fallback פקודות לא מוכרות."""
    if not update.message or not update.message.text:
        return

    txt = update.message.text.strip()
    uid = update.effective_user.id

    # אשף מכירה לאדמין
    if uid in WIZ_SELL:
        st = WIZ_SELL[uid]
        step = st.get("step")

        if step == "wallet":
            if not re.fullmatch(r"0x[a-fA-F0-9]{40}", txt):
                await update.message.reply_text("כתובת ארנק לא תקינה. נסה שוב (0x… 40 hex).")
                return
            st["wallet"] = txt
            st["step"] = "uri"
            await update.message.reply_text(
                "שלב 2/2 — שלח/י את ה־tokenURI:\n"
                "• `ipfs://<CID>` (מומלץ)\n"
                "• או `https://...` קובץ מטאדטה תקין\n"
                "• או רק CID (נתרגם ל-ipfs://CID)\n",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if step == "uri":
            uri_in = txt
            if uri_in.startswith("ipfs://"):
                token_uri = uri_in
            elif re.match(r"^Qm[1-9A-Za-z]{44,}", uri_in):
                token_uri = f"ipfs://{uri_in}"
            else:
                token_uri = uri_in
            st["token_uri"] = token_uri
            st["step"] = "confirm"
            echo = (
                "*אישור נתונים:*\n"
                f"Wallet: `{st['wallet']}`\n"
                f"tokenURI: `{st['token_uri']}`\n\n"
                "כתבו: `confirm` כדי לבצע / `cancel` לביטול.\n"
                "(אפשר גם לצרף הערה אחרי confirm, למשל: `confirm לקוח דמו`)\n"
            )
            await update.message.reply_markdown(echo)
            return

        if step == "confirm":
            low = txt.lower()
            if low.startswith("cancel"):
                reset_wiz(uid)
                await update.message.reply_text("בוטל.")
                return
            if low.startswith("confirm"):
                note = txt[len("confirm"):].strip()
                wallet = st["wallet"]; token_uri = st["token_uri"]
                reset_wiz(uid)
                # בצע
                await _exec_sell(update, wallet, token_uri, note)
                return

    # fallback — אם טקסט מתחיל ב־/ והפקודה לא מוכרת
    if txt.startswith("/"):
        await update.message.reply_text("Unknown command. נסה /adm_help או /mint")

# =========================
# App & Run
# =========================
def build_app():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ping",  ping_cmd))
    app.add_handler(CommandHandler("health",  health_cmd))
    app.add_handler(CommandHandler("mint",  mint_cmd))
    app.add_handler(CommandHandler("adm_help", adm_help))
    app.add_handler(CommandHandler("adm_status", adm_status))
    app.add_handler(CommandHandler("adm_setwebhook", adm_setwebhook))
    app.add_handler(CommandHandler("adm_recent", adm_recent))
    app.add_handler(CommandHandler("adm_sell", adm_sell))
    app.add_handler(CommandHandler("adm_echo", adm_echo))
    # wizard + fallback
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_router))
    # generic fallback for anything else
    app.add_handler(MessageHandler(filters.ALL, lambda *_: None))
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
    _ensure_main_loop()
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
    startup_dump()

    # וובהוק ברמת פרה-פלייט (לא פוסל דיפלוי אם נכשל — תהיה פולינג)
    if MODE == "webhook":
        try:
            ok, msg = asyncio.run(ensure_webhook())
            if not ok:
                log.error(f"ensure_webhook FAILED: {msg}")
        except Exception as e:
            log.error(f"ensure_webhook crashed: {e}")

    print(f"🚀 Admin bot is starting ({MODE})…")
    app = build_app()

    try:
        if MODE == "polling":
            run_polling(app)
        else:
            run_webhook(app)
    except RuntimeError as e:
        # ⛑️ safety net — אם יש בעיית לולאה, עבור לפולינג כדי לא לאבד זמינות
        log.error(f"Webhook failed ({e}). Falling back to POLLING mode…")
        run_polling(app)
