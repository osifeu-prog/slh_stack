# SLH Stack – Bot + API (Testnet)

Ready-to-run **Telegram admin bot** wired to your **FastAPI chain service**.

## What’s inside
- `bot/run_admin_bot.py` – Telegram bot (webhook-ready; auto-sets webhook on boot; logs status).
- `requirements.txt` – dependencies.
- `.env.example` – copy to `.env.secrets` (Railway) or export locally.

## Railway – Services
1. **API**: already deployed → `https://slhstack-production.up.railway.app` (health: `/healthz`).
2. **BOT**: start command `python bot/run_admin_bot.py` with env from `.env.example`.

## Env (bot minimal)
```
TELEGRAM_BOT_TOKEN=...
SLH_API_BASE=https://slhstack-production.up.railway.app
BOT_MODE=webhook
BOT_WEBHOOK_PUBLIC_BASE=https://slhbot-bot.up.railway.app
BOT_WEBHOOK_PATH=/tg
BOT_WEBHOOK_SECRET=sela_secret_123
BOT_PORT=8080
ADMIN_IDS=224223270
```
The bot **auto calls deleteWebhook → setWebhook** on boot. If it fails, it **falls back to polling**.

## Commands
`/ping`, `/adm_help`, `/adm_status`, `/adm_setwebhook`, `/adm_echo <text>`,
`/adm_sell <wallet> <ipfs://CID|https://...> [note...]`, `/adm_recent [N]`, `/adm_post_summary`.

## Local run
```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
export SLH_API_BASE=http://127.0.0.1:8000
export BOT_MODE=polling
python bot/run_admin_bot.py
```
