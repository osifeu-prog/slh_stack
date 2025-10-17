# SLH – Deploy (Railway)

## Services
### 1) SLH_bot
- Start: \python -X utf8 bot/run_admin_bot.py\
- ENV (חובה):
  - \BOT_MODE=webhook\
  - \BOT_WEBHOOK_PUBLIC_BASE=https://slhbot-bot.up.railway.app\  (ללא '/' בסוף)
  - \BOT_WEBHOOK_PATH=/tg\
  - \BOT_WEBHOOK_SECRET=<סוד>\
  - \TELEGRAM_BOT_TOKEN=<טוקן הבוט>\
- אין \BOT_PORT\.

### 2) slh_API
- Start: \uvicorn slh.api:app --host 0.0.0.0 --port \
- אין בו /tg ולא משתני הבוט.

## .env.example
שכפל לקובץ \.env\ בסביבת פיתוח, או הגדר את המשתנים ישירות ב-Railway.

## פיצ'רים שנוספו
- /start עם כפתורי RTL.
- ⚡ "קנה/י SELA" → זרימת \/mint\ (ERC-20, BSC Testnet).
- דרישת \web3\ ב-requirements.

## הערות אבטחה
- אל תדחוף \.env\ לריפו.
- המפתח הפרטי \TREASURY_PRIVATE_KEY\ נשאר רק ב-Railway ENV.