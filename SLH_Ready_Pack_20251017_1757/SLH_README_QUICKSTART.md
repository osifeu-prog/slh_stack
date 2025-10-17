# SLH Admin Bot — Quick Start (Windows, PowerShell)

1. Extract this ZIP.
2. Open PowerShell in the extracted folder and run:
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ./SLH-Bot-Bootstrap.ps1
   ```
3. When prompted, paste your `TELEGRAM_BOT_TOKEN` and your public `https` URL (Railway/Vercel/ngrok).
4. The script creates `.venv`, installs deps, sets the Telegram webhook with a secret, and runs the bot.
5. In Telegram, send `/start` or `/ping` to your bot. For admin actions: `/adm_setwebhook`, `/adm_status`, `/adm_recent`.

## Environment
- `BOT_MODE` default: `webhook` (falls back to polling automatically if webhook fails).
- `BOT_WEBHOOK_PUBLIC_BASE` (e.g., `https://yourapp.up.railway.app`)
- `BOT_WEBHOOK_PATH` default `/tg`
- `BOT_WEBHOOK_SECRET` must be letters/digits/_-
- `BOT_PORT` default `8080`
- `SLH_API_BASE` default `https://slhstack-production.up.railway.app`
