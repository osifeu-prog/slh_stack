# SLH Stack – Testnet Pack (Railway-ready)

This pack ships:
- **API** (FastAPI) with `/healthz`, `/v1/chain/mint-demo`, `/v1/chain/grant-sela`
- **BOT** (python-telegram-bot 20.x) ready for webhook with auto `setWebhook` on boot
- `railway.toml` for two Railway services
- `.env.example` for local runs

## Deploy (Railway)

1. Push to GitHub.
2. Create service **api** and **bot** from this repo (Railway will read `railway.toml`).
3. Set variables:

**API**
- `BSC_RPC_URL=https://bsc-testnet-rpc.publicnode.com`
- `NFT_CONTRACT=0x8AD1de67648dB44B1b1D0E3475485910CedDe90b`
- `CHAIN_ID=97`
- *(optional for real on-chain)* `TREASURY_PRIVATE_KEY=0x...`

**BOT**
- `TELEGRAM_BOT_TOKEN=...`
- `SLH_API_BASE=https://<api>.up.railway.app`
- `BOT_WEBHOOK_PUBLIC_BASE=https://<bot>.up.railway.app`
- `BOT_WEBHOOK_PATH=/tg`
- `BOT_WEBHOOK_SECRET=sela_secret_123`  (A-Z a-z 0-9 _ -)
- `PORT=8080`
- `ADMIN_IDS=224223270`

## Verify

- API: `GET https://<api>.up.railway.app/healthz` -> `{"ok":true,...}`
- Bot: in Telegram -> `/adm_status`, `/adm_setwebhook`, `/ping`, `/adm_sell <wallet> ipfs://CID`

