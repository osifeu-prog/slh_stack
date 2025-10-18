import os, asyncio, logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from web3 import Web3

# ---------- Logging robust (accepts "info"/"INFO"/numeric like 20) ----------
def _resolve_log_level():
    val = os.environ.get("LOG_LEVEL", "INFO")
    try:
        return int(val)
    except (ValueError, TypeError):
        return logging._nameToLevel.get(str(val).upper(), logging.INFO)


def _is_debug() -> bool:
    val = os.environ.get("DEBUG", "0")
    return str(val).strip().lower() in ("1","true","yes","on")

# quiet web3 unless debug
if not _is_debug():
    logging.getLogger("web3").setLevel(logging.WARNING)
else:
    logger.setLevel(logging.DEBUG)
logger = logging.getLogger("slh.bot")

# ---------- ENV helpers ----------
def _env(k: str, d: Optional[str] = None) -> Optional[str]:
    return os.environ.get(k, d)

def _need(k: str) -> str:
    v = _env(k)
    if not v:
        raise RuntimeError(f"Missing env: {k}")
    return v

# ---------- ERC-721 ABIs ----------
def _erc721_mint_abi():
    return [{
        "inputs":[{"internalType":"address","name":"to","type":"address"}],
        "name":"safeMint","outputs":[],
        "stateMutability":"nonpayable","type":"function"
    }]

def _erc721_tokenuri_abi():
    return [{
        "inputs":[{"internalType":"uint256","name":"tokenId","type":"uint256"}],
        "name":"tokenURI","outputs":[{"internalType":"string","name":"","type":"string"}],
        "stateMutability":"view","type":"function"
    }]

# ---------- utils ----------
def _fetch_token_id_from_receipt(w3: Web3, contract_address: str, tx_hash_hex: str) -> Optional[int]:
    sig = Web3.keccak(text="Transfer(address,address,uint256)").hex()
    rc = w3.eth.get_transaction_receipt(tx_hash_hex)
    for lg in rc.logs:
        if lg["address"].lower() == Web3.to_checksum_address(contract_address).lower():
            t0 = lg["topics"][0].hex() if hasattr(lg["topics"][0], "hex") else str(lg["topics"][0])
            if t0.lower() == sig.lower() and len(lg["topics"]) >= 4:
                return int(lg["topics"][3].hex(), 16)
    return None

def _get_w3():
    rpc = _need("BSC_RPC_URL")
    import math
    try:
        to = int(os.environ.get("BSC_RPC_TIMEOUT","30"))
    except Exception:
        to = 30
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": to}))
    if not w3.is_connected():
        raise RuntimeError("RPC לא זמין")
    return w3# ---------- UI ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("⚡ קנה/י SELA (NFT)", callback_data="buy_sela_nft"),
         InlineKeyboardButton("🚀 הנפקה/מכירה", callback_data="sell_wizard")],
        [InlineKeyboardButton("📊 סטטוס", callback_data="status"),
         InlineKeyboardButton("ℹ️ עזרה", callback_data="help")]
    ]
    text = ("ברוך/ה הבא/ה ל־<b>SLH Admin Bot</b> ✨\n"
            "כאן מבצעים mint ל־NFT (ERC-721) על BSC Testnet.\n\n"
            "בחר/י פעולה:")
    msg = update.message or update.effective_message
    await msg.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def on_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = (q.data or "").strip()
    await q.answer()
    if data == "buy_sela_nft":
        await mint_start(update, context)
    elif data == "sell_wizard":
        await q.message.reply_text("🔧 בקרוב: אשף הנפקה/מכירה.")
    elif data == "status":
        await q.message.reply_text("✅ הבוט פעיל. נסה/י /mint")
    elif data == "help":
        await q.message.reply_text("עזרה: /mint לנפק NFT, /tokenId לקבלת מזהה אחרון, /tokenURI לקבלת ה-URI.")
    else:
        await q.message.reply_text("⌛ בקרוב…")

# ---------- Commands ----------
async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await (update.message or update.effective_message).reply_text("pong 🟢")

async def mint_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_wallet_for_mint_nft"] = True
    await (update.message or update.effective_message).reply_text("שלח/י כתובת ארנק BSC (0x…) לקבלת NFT (טסטנט).")

async def mint_wallet_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_wallet_for_mint_nft"):
        return
    addr = (update.message.text or "").strip()
    if not addr.startswith("0x") or len(addr) != 42:
        await update.message.reply_text("❗ כתובת לא תקינה. נא שלח/י כתובת בפורמט 0x...")
        return
    context.user_data["awaiting_wallet_for_mint_nft"] = False
    logger.info("[MINT] start | to=%s", addr)
    await update.message.reply_text("⏳ מבצע mint ל-NFT על BSC Testnet…")
    loop = asyncio.get_running_loop()
    try:
        tx_hash = await loop.run_in_executor(None, erc721_mint_from_treasury, addr)
        context.user_data["last_mint_tx"] = tx_hash
        logger.info("[MINT] sent | tx=%s", tx_hash)
        # נסה לאסוף tokenId מהקבלה
        try:
            w3 = _get_w3()
            tid = _fetch_token_id_from_receipt(w3, _need("NFT_CONTRACT"), tx_hash)
            if tid is not None:
                context.user_data["last_token_id"] = tid
                await update.message.reply_text(f"✅ NFT הונפק!\nTokenID: <code>{tid}</code>\nTx: <code>{tx_hash}</code>", parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"✅ NFT הונפק!\n(לא אותר tokenId מהקבלה)\nTx: <code>{tx_hash}</code>", parse_mode=ParseMode.HTML)
        except Exception as ie:
            logger.exception("[MINT] parse receipt failed: %s", ie)
            await update.message.reply_text(f"✅ NFT הונפק!\n(שחזור tokenId נדחה: {ie})\nTx: <code>{tx_hash}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.exception("[MINT] failed: %s", e)
        await update.message.reply_text(f"❗ שגיאה בביצוע:\n{e}")

def erc721_mint_from_treasury(to_addr: str) -> str:
    import time
    w3 = _get_w3()
    chain_id      = int(_env("CHAIN_ID", "97"))
    contract_addr = _need("NFT_CONTRACT")
    pk            = _need("TREASURY_PRIVATE_KEY")
    acct = w3.eth.account.from_key(pk)
    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=_erc721_mint_abi())
    fn = contract.get_function_by_name("safeMint")(Web3.to_checksum_address(to_addr))

    max_fee   = w3.to_wei(_env("MAX_FEE_GWEI","2"), "gwei")
    max_prio  = w3.to_wei(_env("MAX_PRIO_FEE_GWEI","1"), "gwei")

    attempts = int(_env("MINT_RETRIES","5"))
    back0    = float(_env("MINT_BACKOFF_SECONDS","1"))
    last_exc = None

    for i in range(attempts):
        t0 = time.time()
        try:
            nonce = w3.eth.get_transaction_count(acct.address)
            tx = fn.build_transaction({
                "from": acct.address,
                "nonce": nonce,
                "chainId": chain_id,
                "gas": 220000,
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": max_prio,
            })
            signed  = acct.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
            logger.debug("[MINT] sent nonce=%s maxFee=%s maxPrio=%s tx=%s", nonce, max_fee, max_prio, tx_hash.hex())

            rc = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=int(_env("RECEIPT_TIMEOUT","180")))
            dt = time.time() - t0
            gas_used = getattr(rc, "gasUsed", None)
            blk = getattr(rc, "blockNumber", None)
            cg  = getattr(rc, "cumulativeGasUsed", None)
            logger.info("[MINT] receipt status=%s block=%s gas=%s cumGas=%s dt=%.2fs tx=%s", rc.status, blk, gas_used, cg, dt, tx_hash.hex())
            if rc.status != 1:
                raise RuntimeError(f"tx failed: {tx_hash.hex()}")

            # נסיון להפיק tokenId בלוגים, נשאיר גם לוג לטובת דיבוג
            try:
                tid = _fetch_token_id_from_receipt(w3, contract_addr, tx_hash.hex())
                logger.debug("[MINT] parsed tokenId=%s", tid)
            except Exception as ie:
                logger.debug("[MINT] parse tokenId failed: %s", ie)

            return tx_hash.hex()
        except Exception as e:
            last_exc = e
            wait = back0 * (2 ** i)
            logger.warning("[MINT] attempt %s/%s failed: %s | backoff %.1fs", i+1, attempts, e, wait)
            time.sleep(wait)

    raise RuntimeError(f"mint failed after {attempts} attempts: {last_exc}")
async def debug_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keys = ["DEBUG","LOG_LEVEL","BSC_RPC_URL","CHAIN_ID","NFT_CONTRACT","RECEIPT_TIMEOUT","MINT_RETRIES","MINT_BACKOFF_SECONDS","MAX_FEE_GWEI","MAX_PRIO_FEE_GWEI"]
    vals = []
    for k in keys:
        v = os.environ.get(k, "")
        if k == "BSC_RPC_URL" and v:
            v = v[:20] + "..."   # קיצור תצוגה
        if k == "TREASURY_PRIVATE_KEY":  # ליתר בטחון לא נציג
            v = "***"
        vals.append(f"{k}={v}")
    await (update.message or update.effective_message).reply_text("DEBUG="+("ON" if _is_debug() else "OFF")+"\n"+"\n".join(vals))