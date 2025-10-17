# SLH Stack — Testnet Go‑Live Pack

This pack contains a clean **Telegram admin bot** + pointers for your **FastAPI** service, ready for local dev and Railway deploy.  
Target chain: **BNB Smart Chain Testnet (chainId 97)**

---

## 0) Contracts & Network (reference)
- **Network:** BSC Testnet (97)
- **NFT (ERC‑721) Contract:** `0x8AD1de67648dB44B1b1D0E3475485910CedDe90b`
- ABI path expected: `abi/SLHNFT.json` (keep your current file)
- Example metadata CID: `QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq`

---

## 1) Repo layout

```
.
├─ abi/
│  └─ SLHNFT.json            # (your existing ABI file, not overwritten by this pack)
├─ bot/
│  └─ run_admin_bot.py       # Telegram bot, webhook/polling, admin commands
├─ scripts/
│  └─ quick_check.py         # Small read‑only checks against the NFT contract
├─ tools/
│  └─ check_env.py           # Prints/validates required env vars
├─ run_api.py                # (already in your repo — your API service)
├─ requirements.txt          # Ensure it has: python-telegram-bot[webhooks], fastapi, uvicorn, web3, httpx
├─ .env.example              # Fill and copy to .env.secrets locally or to Railway Variables
├─ Procfile.api              # Railway process for API
└─ Procfile.bot              # Railway process for Bot
```

---

## 2) Environment variables

Copy `.env.example` to `.env.secrets` **locally** (don’t commit secrets) or paste **the same keys** into Railway → Variables.

### API (already live for you)
```
BSC_RPC_URL=https://bsc-testnet-rpc.publicnode.com
CHAIN_ID=97
NFT_CONTRACT=0x8AD1de67648dB44B1b1D0E3475485910CedDe90b
TREASURY_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
DEFAULT_WALLET=0x693db6c817083818696a7228aEbfBd0Cd3371f02
DEFAULT_META_CID=QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq
SELA_AMOUNT=0.15984
```

### Bot
```
TELEGRAM_BOT_TOKEN=8225059465:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
SLH_API_BASE=https://slhstack-production.up.railway.app
DEFAULT_WALLET=0x693db6c817083818696a7228aEbfBd0Cd3371f02
DEFAULT_META_CID=QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq
SELA_AMOUNT=0.15984
ADMIN_IDS=224223270

BOT_MODE=webhook
BOT_WEBHOOK_PUBLIC_BASE=https://slhbot-bot.up.railway.app
BOT_WEBHOOK_PATH=/tg
BOT_WEBHOOK_SECRET=sela_secret_123
BOT_PORT=8081
```

**Notes**
- `ADMIN_IDS` = comma separated Telegram user IDs allowed to use admin commands.
- `BOT_WEBHOOK_PUBLIC_BASE` **must** be **https** (Railway bot service domain).
- `BOT_WEBHOOK_SECRET` must be URL/header‑safe: letters, digits, `_` or `-`.
- `BOT_PORT` should match Railway **Target Port** of the bot service.

Quick verification:
```bash
python tools/check_env.py
```

---

## 3) Local run

**Terminal A (API):**
```bash
python -X utf8 run_api.py
```

**Terminal B (Bot):**
```bash
# Polling (simple for local):
set BOT_MODE=polling
python -X utf8 bot/run_admin_bot.py

# Webhook (if exposing https via ngrok/cloudflared):
set BOT_MODE=webhook
python -X utf8 bot/run_admin_bot.py
```

---

## 4) Railway (two services)

### A) API service
- Start: `python -X utf8 run_api.py`
- Port: **8080**
- Vars: the **API** block above

### B) Bot service
- Start: `python -X utf8 bot/run_admin_bot.py`
- Port: **8081**
- Vars: the **Bot** block above

---

## 5) Admin commands

- `/start` — hello
- `/ping` — pong
- `/adm_help` — list admin commands
- `/adm_sell <wallet> <ipfs://CID|https://...> [note]` — mint + grant SELA via API; returns both TX links
- `/adm_recent [N]` — recent events
- `/adm_post_summary` — posts go‑live summary card

API the bot calls:
- `POST /v1/chain/mint-demo` `{ "to_wallet": "...", "token_uri": "ipfs://..." }`
- `POST /v1/chain/grant-sela` `{ "to_wallet": "...", "amount": "..." }`

---

## 6) Troubleshooting
- Webhook needs **https** URL and safe `BOT_WEBHOOK_SECRET`
- On Railway, **set BOT_PORT to a number** (e.g. 8081) and Networking → Target Port = 8081
- 401 from Telegram → token invalid; use @BotFather to regenerate
- API 404 → verify `SLH_API_BASE`

Good luck 🚀
