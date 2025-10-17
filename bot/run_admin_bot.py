
import os, io, zipfile, textwrap
from dotenv import load_dotenv
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN","").strip()
MODE    = os.getenv("BOT_MODE","webhook").strip().lower()
PORT    = int(os.getenv("BOT_PORT","8081"))
PATH    = os.getenv("BOT_WEBHOOK_PATH","/tg")
SECRET  = os.getenv("BOT_WEBHOOK_SECRET","")
PUBLIC  = os.getenv("BOT_WEBHOOK_PUBLIC_BASE","")
API_BASE= os.getenv("SLH_API_BASE","http://127.0.0.1:8000")
DEFAULT_META_CID = os.getenv("DEFAULT_META_CID","")
SELA_AMOUNT      = os.getenv("SELA_AMOUNT","0.15984")

if not TOKEN:
    print("TELEGRAM_BOT_TOKEN missing")
    raise SystemExit(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Bot is up. Try /ping or /adm_help")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def adm_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = textwrap.dedent("""
    *Admin Menu*
    1) /adm_sell <wallet> <ipfs://cid|-> [note...]  — mint + grant
    2) /adm_backup  — zip & download project (current dir)
    """).strip()
    await update.message.reply_text(txt, parse_mode="Markdown")

async def adm_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buf = io.BytesIO()
    base_dir = os.getcwd()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(base_dir):
            if ".venv" in root or ".git" in root or "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".zip"):
                    continue
                p = os.path.join(root, f)
                arc = os.path.relpath(p, base_dir)
                try:
                    with open(p, "rb") as fh:
                        z.writestr(arc, fh.read())
                except Exception:
                    pass
    buf.seek(0)
    await update.message.reply_document(document=InputFile(buf, filename="slh_backup.zip"),
                                        caption="SLH project backup")

async def adm_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text("Usage: /adm_sell <wallet> <ipfs://CID|-> [note]")
        return
    wallet = args[0]
    uri_or_dash = args[1]
    token_uri = f"ipfs://{DEFAULT_META_CID}" if uri_or_dash == "-" else uri_or_dash

    # 1) mint
    try:
        import httpx
        payload = {"to_wallet": wallet, "token_uri": token_uri}
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{API_BASE}/v1/chain/mint-demo", json=payload)
            r.raise_for_status()
            mint_tx = r.json().get("tx")
    except Exception as e:
        await update.message.reply_text(f"Mint failed: {e}")
        return

    # 2) grant SELA
    try:
        import httpx
        payload = {"to_wallet": wallet, "amount": SELA_AMOUNT}
        async with httpx.AsyncClient(timeout=60) as client:
            r2 = await client.post(f"{API_BASE}/v1/chain/grant-sela", json=payload)
            r2.raise_for_status()
            sela_tx = r2.json().get("tx")
    except Exception as e:
        sela_tx = None

    txt = f"✅ Mint TX: {mint_tx}\n"
    if sela_tx:
        txt += f"✅ SELA TX: {sela_tx}\n"
    else:
        txt += "⚠️ SELA not configured/failed\n"
    await update.message.reply_text(txt)

def build_app():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("adm_help", adm_help))
    app.add_handler(CommandHandler("adm_backup", adm_backup))
    app.add_handler(CommandHandler("adm_sell", adm_sell))
    return app

def main():
    app = build_app()
    if MODE == "webhook":
        if not PUBLIC.startswith("https://"):
            raise SystemExit("BOT_WEBHOOK_PUBLIC_BASE must be https for webhook mode")
        print("🚀 Admin bot is starting (webhook)…")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            secret_token=SECRET or None,
            webhook_url=f"{PUBLIC}{PATH}",
            allowed_updates=None,
        )
    else:
        print("🚀 Admin bot is starting (polling)…")
        app.run_polling(allowed_updates=None)

if __name__ == "__main__":
    main()
