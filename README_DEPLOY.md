# SLH – Deploy (Railway)

## Services
### 1) SLH_bot
- Start: \python -X utf8 bot/run_admin_bot.py\
- ENV (חובה):
  - \BOT_MODE=webhook\
  - \BOT_WEBHOOK_PUBLIC_BASE=https://slhbot-bot.up.railway.app\  (ללא '/' בסוף)
  - \BOT_WEBHOOK_PATH=/tg\
  - \BOT_WEBHOOK_SECRET=<סוד>\
  - \TELEGRAM_BOT_TOKEN=<טוקן מה@BotFather>\
  - \BSC_RPC_URL\, \CHAIN_ID=97\, \TOKEN_CONTRACT\, \TREASURY_PRIVATE_KEY\, \SELA_AMOUNT=0.15984\
- אין \BOT_PORT\.

### 2) slh_API
- Start: \uvicorn slh.api:app --host 0.0.0.0 --port \
- לשים ENV רלוונטיים ל-API בלבד.

## פיצ'רים בקוד
- \/start\ עם כפתורים בעברית (RTL).
- כפתור **⚡ קנה/י SELA** מחובר לזרימת \/mint\ (ERC-20 על BSC Testnet).
- רישום הנדלרים: \CallbackQueryHandler\, \CommandHandler('mint', ...)\, \MessageHandler(... mint_wallet_collector)\.
- \equirements.txt\ כולל \web3\.

## אבטחה
- אל תדחוף \.env\ לריפו.
- שמור \TREASURY_PRIVATE_KEY\ ויתר סודות רק ב-ENV של Railway.