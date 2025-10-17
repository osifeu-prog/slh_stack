# SLH – API + Telegram Bot (Testnet scaffold)

This repo contains a minimal setup to run your FastAPI chain endpoints **and** a Telegram admin bot on Railway (or locally).

## Structure
```
.
├─ run_api.py                 # FastAPI app with /healthz, /v1/chain/mint-demo, /v1/chain/grant-sela
├─ bot/
│  └─ run_admin_bot.py        # Telegram bot (webhook/polling), /adm_sell, /adm_backup, etc.
├─ abi/
│  └─ SLHNFT.json             # Minimal ABI for minting
├─ scripts/
│  └─ quick_check.py          # Helper: ownerOf/tokenURI
├─ requirements.txt
├─ .gitignore
└─ .env.example               # Copy to .env locally (DON'T commit secrets)
```

## Quick local run

1) Create & fill `.env` (see `.env.example`), at least:
```
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC...      # from @BotFather
BOT_MODE=webhook                      # or "polling"
BOT_PORT=8081
BOT_WEBHOOK_PATH=/tg
BOT_WEBHOOK_SECRET=s3la-secret-verify
BOT_WEBHOOK_PUBLIC_BASE=https://<your-https-url>   # required for webhook mode

# API base for bot calls
SLH_API_BASE=http://127.0.0.1:8000

# On-chain (BSC Testnet)
BSC_RPC_URL=https://bsc-testnet-rpc.publicnode.com
NFT_CONTRACT=0x8AD1de67648dB44B1b1D0E3475485910CedDe90b  # contract owner must match private key below
TREASURY_PRIVATE_KEY=0x...                                # owner key (DO NOT COMMIT)
DEFAULT_WALLET=0x693db6c817083818696a7228aEbfBd0Cd3371f02
DEFAULT_META_CID=QmbsDJMcYvwu5NrnWFC9vieUTFuuAPRMNSjmrVmnm5bJeq
SELA_AMOUNT=0.15984

# Optional ERC-20 SELA token transfer (grant-sela)
SELA_TOKEN_ADDRESS=0x0000000000000000000000000000000000000000
```

2) Install deps and run API:
```
python -m venv .venv
# Windows:
.\.venv\Scriptsctivate
pip install -r requirements.txt
uvicorn run_api:app --host 0.0.0.0 --port 8000
```

3) In another shell, run bot:
```
python bot/run_admin_bot.py
```

### Endpoints
- `GET /healthz` → `{ "ok": true }`
- `POST /v1/chain/mint-demo` JSON: `{ "to_wallet": "...", "token_uri": "ipfs://..." }`
- `POST /v1/chain/grant-sela` JSON: `{ "to_wallet": "...", "amount": "0.15984" }` (requires `SELA_TOKEN_ADDRESS`)

### Railway
- Create two services from the same repo: **api** and **bot**.
- **api** Start Command: `uvicorn run_api:app --host 0.0.0.0 --port $PORT`
- **bot** Start Command: `python bot/run_admin_bot.py`
- Set all ENV vars in Railway **Variables** (English keys only).

**Security**: Never commit `.env` or private keys. Use Railway environment variables instead.
