import os, asyncio, logging, json
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from web3 import Web3

logger = logging.getLogger("slh.bot")
logging.basicConfig(level=getattr(logging, os.environ.get("LOG_LEVEL","INFO"), logging.INFO))

def _env(k: str, d: Optional[str] = None) -> Optional[str]: return os.environ.get(k, d)
def _get_required(k: str) -> str:
    v = _env(k)
    if not v: raise RuntimeError(f"Missing env: {k}")
    return v

def _erc721_mint_abi():
    return [{"inputs":[{"internalType":"address","name":"to","type":"address"}],"name":"safeMint","outputs":[],"stateMutability":"nonpayable","type":"function"}]

def _erc721_tokenuri_abi():
    return [{"inputs":[{"internalType":"uint256","name":"tokenId","type":"uint256"}],"name":"tokenURI","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"}]

def _fetch_token_id_from_receipt(w3: Web3, contract_address: str, tx_hash_hex: str) -> Optional[int]:
    sig = Web3.keccak(text="Transfer(address,address,uint256)").hex()
    receipt = w3.eth.get_transaction_receipt(tx_hash_hex)
    for lg in receipt.logs:
        if lg["address"].lower() == Web3.to_checksum_address(contract_address).lower():
            t0 = lg["topics"][0].hex() if hasattr(lg["topics"][0],"hex") else str(lg["topics"][0])
            if t0.lower() == sig.lower() and len(lg["topics"]) >= 4:
                return int(lg["topics"][3].hex(), 16)
    return None

def _get_w3_and_contract_for_tokenuri():
    rpc = _get_required("BSC_RPC_URL"); contract_addr = _get_required("NFT_CONTRACT")
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected(): raise RuntimeError("RPC לא זמין")
    c = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=_erc721_tokenuri_abi())
    return w3, c

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("⚡ קנה/י SELA (NFT)", callback_data="buy_sela_nft"),
           InlineKeyboardButton("🚀 הנפקה/מכירה", callback_data="sell_wizard")],
          [InlineKeyboardButton("📊 סטטוס", callback_data="status"),
           InlineKeyboardButton("ℹ️ עזרה", callback_data="help")]]
    text = ("ברוך/ה הבא/ה ל־<b>SLH Admin Bot</b> ✨\n"
            "כאן מבצעים mint ל־NFT (ERC-721) ב־BSC Testnet.\n\n"
            "בחר/י פעולה:")
    msg = update.message or update.effective_message
    await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def on_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; data = (q.data or "").strip(); await q.answer()
    if data == "buy_sela_nft": await mint_nft_start(update, context)
    elif data == "sell_wizard": await q.message.reply_text("🔧 בקרוב: אשף הנפקה/מכירה.")
    elif data == "status": await q.message.reply_text("✅ הבוט פעיל. נסה/י /mint")
    elif data == "help": await q.message.reply_text("עזרה: /mint לנפק NFT, /tokenId לקבלת מזהה אחרון, /tokenURI לקבלת ה-URI.")
    else: await q.message.reply_text("⌛ בקרוב…")

async def mint_nft_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_wallet_for_mint_nft"] = True
    await (update.message or update.effective_message).reply_text("שלח/י כתובת ארנק BSC (0x…) לקבלת NFT (טסטנט).")

async def mint_nft_wallet_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_wallet_for_mint_nft"): return
    addr = (update.message.text or "").strip()
    if not addr.startswith("0x") or len(addr) != 42:
        await update.message.reply_text("❗ כתובת לא תקינה. נא שלח/י כתובת בפורמט 0x..."); return
    context.user_data["awaiting_wallet_for_mint_nft"] = False
    logger.info("[MINT] start | to=%s", addr)
    await update.message.reply_text("⏳ מבצע mint ל-NFT על BSC Testnet…")
    loop = asyncio.get_running_loop()
    try:
        tx_hash = await loop.run_in_executor(None, erc721_mint_from_treasury, addr)
        context.user_data["last_mint_tx"] = tx_hash; logger.info("[MINT] sent | tx=%s", tx_hash)
        try:
            rpc = _get_required("BSC_RPC_URL"); contract_addr = _get_required("NFT_CONTRACT")
            w3 = Web3(Web3.HTTPProvider(rpc))
            if w3.is_connected():
                tid = _fetch_token_id_from_receipt(w3, contract_addr, tx_hash)
                if tid is not None:
                    context.user_data["last_token_id"] = tid
                    await update.message.reply_text(f"✅ NFT הונפק!\nTokenID: <code>{tid}</code>\nTx: <code>{tx_hash}</code>", parse_mode=ParseMode.HTML)
                else:
                    await update.message.reply_text(f"✅ NFT הונפק!\n(לא אותר tokenId מהקבלה)\nTx: <code>{tx_hash}</code>", parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"✅ NFT הונפק!\n(אין חיבור RPC לזיהוי tokenId כעת)\nTx: <code>{tx_hash}</code>", parse_mode=ParseMode.HTML)
        except Exception as ie:
            logger.exception("[MINT] parse receipt failed: %s", ie)
            await update.message.reply_text(f"✅ NFT הונפק!\n(שחזור tokenId נדחה: {ie})\nTx: <code>{tx_hash}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.exception("[MINT] failed: %s", e)
        await update.message.reply_text(f"❗ שגיאה בביצוע:\n{e}")

def erc721_mint_from_treasury(to_addr: str) -> str:
    rpc = _get_required("BSC_RPC_URL"); chain_id = int(_env("CHAIN_ID","97"))
    contract_addr = _get_required("NFT_CONTRACT"); pk = _get_required("TREASURY_PRIVATE_KEY")
    logger.info("[TX] prepare | rpc=%s | chain_id=%s | contract=%s", rpc, chain_id, contract_addr)
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected(): raise RuntimeError("RPC לא זמין")
    acct = w3.eth.account.from_key(pk)
    abi = _erc721_mint_abi(); contract = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=abi)
    fn = contract.get_function_by_name("safeMint")(Web3.to_checksum_address(to_addr))
    nonce = w3.eth.get_transaction_count(acct.address)
    tx = fn.build_transaction({"from":acct.address,"nonce":nonce,"chainId":chain_id,"gas":220000,"maxFeePerGas":w3.to_wei("2","gwei"),"maxPriorityFeePerGas":w3.to_wei("1","gwei")})
    signed = acct.sign_transaction(tx); tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1: raise RuntimeError(f"tx failed: {tx_hash.hex()}")
    return tx_hash.hex()

async def cmd_tokenId(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data.get("last_token_id")
    if tid is not None:
        await update.message.reply_text(f"🔖 tokenId האחרון שלך: <code>{tid}</code>", parse_mode=ParseMode.HTML); return
    txh = context.user_data.get("last_mint_tx")
    if not txh: await update.message.reply_text("אין tokenId שמור עדיין. בצע/י mint קודם."); return
    try:
        rpc = _get_required("BSC_RPC_URL"); contract_addr = _get_required("NFT_CONTRACT")
        w3 = Web3(Web3.HTTPProvider(rpc))
        if not w3.is_connected(): await update.message.reply_text("RPC לא זמין כרגע לשחזור tokenId."); return
        tid = _fetch_token_id_from_receipt(w3, contract_addr, txh)
        if tid is None: await update.message.reply_text("לא אותר tokenId מהקבלה."); return
        context.user_data["last_token_id"] = tid
        await update.message.reply_text(f"🔖 tokenId האחרון שלך: <code>{tid}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.exception("[tokenId] failed: %s", e); await update.message.reply_text(f"שגיאה בשחזור tokenId: {e}")

async def cmd_tokenURI(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data.get("last_token_id")
    if tid is None: await update.message.reply_text("אין tokenId שמור. הרץ/י /tokenId קודם, או בצע/י mint."); return
    try:
        w3, c = _get_w3_and_contract_for_tokenuri()
        uri = c.get_function_by_name("tokenURI")(tid).call()
        await update.message.reply_text(f"🔗 tokenURI:\n<code>{uri}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.exception("[tokenURI] failed: %s", e); await update.message.reply_text(f"שגיאה בקריאת tokenURI: {e}")

def build_app():
    TOKEN = _get_required("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("mint", mint_nft_start))
    app.add_handler(CommandHandler("tokenId", cmd_tokenId))
    app.add_handler(CommandHandler("tokenURI", cmd_tokenURI))
    app.add_handler(CallbackQueryHandler(on_cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mint_nft_wallet_collector))
    return app

async def _run_webhook(app):
    public = _get_required("BOT_WEBHOOK_PUBLIC_BASE"); path = _env("BOT_WEBHOOK_PATH","/tg")
    secret = _get_required("BOT_WEBHOOK_SECRET"); port = int(_env("PORT","8080"))
    await app.initialize(); await app.start()
    await app.updater.start_webhook(listen="0.0.0.0", port=port, url_path=path.lstrip("/"),
                                    secret_token=secret, webhook_url=f"{public}{path}")
    logger.info("[WEBHOOK] listening on %s%s", public, path)
    await app.updater.idle(); await app.stop(); await app.shutdown()

def main():
    mode = _env("BOT_MODE","webhook").lower(); app = build_app()
    if mode == "polling": app.run_polling(close_loop=False)
    else: asyncio.run(_run_webhook(app))

if __name__ == "__main__": main()