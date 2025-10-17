מעולה 💪 הנה שני קבצים חדשים שתוסיף לתיקיית הפרויקט שלך (`/app/bot/` או השורש בגיט):

---

### 🧭 `README.md` (מעודכן ומוכן לגיט)

````markdown
# 🪙 SLH Admin Bot

בוט טלגרם לניהול רשת ה־SELA על גבי **Binance Smart Chain (Testnet)**.  
הבוט מאפשר **מינטינג של NFT** והענקת טוקני SELA אוטומטית דרך API מאובטח.

---

## 🚀 תכונות עיקריות

- 🟢 **מצב Webhook מלא** (או Polling fallback)
- 🧩 `/mint <wallet>` — הנפקת NFT למשתתף והעברת SELA
- 🪙 `/adm_sell` — מכירה / מינט + גרנט למשתמש (אשף דו־שלבי)
- ⚙️ `/adm_status` — סטטוס מלא של ההרצה והסביבה
- 📡 `/adm_setwebhook` — ריענון וחיבור מחדש של webhook
- 🧾 `/adm_recent` — הצגת אירועים אחרונים או שמירה לקובץ
- 💬 `/adm_echo` — בדיקת תקשורת
- ❤️ `/health` — בדיקת API `/healthz`
- 🧠 מנגנון לוגים אוטומטי (`/app/botdata/logs`)
- 🔁 התאוששות אוטומטית מפגיעות event loop / webhook
- 🔐 ניהול הרשאות אדמין לפי `ADMIN_IDS`

---

## 📦 משתני סביבה חיוניים

| משתנה | תיאור |
|--------|--------|
| `TELEGRAM_BOT_TOKEN` | טוקן מה־BotFather |
| `SLH_API_BASE` | כתובת API (למשל: `https://slhstack-production.up.railway.app`) |
| `BOT_MODE` | `webhook` או `polling` |
| `BOT_WEBHOOK_PUBLIC_BASE` | קישור HTTPS ציבורי של Railway |
| `BOT_WEBHOOK_PATH` | נתיב webhook (למשל `/tg`) |
| `BOT_WEBHOOK_SECRET` | מחרוזת סודית לאימות Telegram |
| `DEFAULT_WALLET` | ארנק ברירת מחדל למבחן |
| `DEFAULT_META_CID` | CID של ה־NFT הדיפולטי (IPFS) |
| `SELA_AMOUNT` | כמות SELA להעברה |
| `ADMIN_IDS` | רשימת מזהי משתמש (User ID) מופרדים בפסיק |
| `BOT_LOG_DIR` | נתיב שמירת לוגים |

---

## 🧠 פקודות חשובות

| פקודה | שימוש |
|--------|--------|
| `/start` | הודעת פתיחה ומשפט הסבר |
| `/ping` | בדיקת חיים |
| `/health` | בדיקת חיבור לשרת SELA |
| `/mint <wallet>` | מינטינג לכתובת (למשתתפים) |
| `/adm_help` | רשימת פקודות אדמין |
| `/adm_sell` | אשף מינט + העברה |
| `/adm_recent save` | שמירת לוגים לקובץ |
| `/adm_setwebhook` | חידוש webhook |
| `/adm_status` | בדיקת הגדרות |
| `/adm_echo` | הדפסה חוזרת |

---

## 🧪 בדיקת מינטינג (Testnet)

1. ודא ש־MetaMask שלך מחובר לרשת **BSC Testnet**.  
   ```shell
   Network: BSC Testnet
   RPC: https://data-seed-prebsc-1-s1.binance.org:8545
   Chain ID: 97
````

2. שלח לבוט:

   ```
   /mint 0x693db6c817083818696a7228aEbfBd0Cd3371f02
   ```

3. תקבל חזרה:

   * קישורים ל־BscScan של העסקאות
   * tokenURI של ה־NFT
   * סיכום האירוע (נשמר גם בלוג)

---

## 📁 לוגים ותחזוקה

* לוגים נשמרים תחת:

  ```
  /app/botdata/logs/session-YYYYMMDD-HHMMSS.log
  ```
* לצפייה מהבוט:

  ```
  /adm_recent 10
  /adm_recent save
  ```

---

## 🧑‍💻 פקודות להרצה מקומית

```bash
# יצירת סביבה והרצה
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# הפעלה מקומית (polling)
export BOT_MODE=polling
python bot/run_admin_bot.py
```

---

## 🧩 טסטים מומלצים

* ✅ `/health` — לוודא תקשורת מול ה־API
* ✅ `/mint` — לבדוק הנפקת NFT
* ✅ `/adm_sell` — לבדוק מינט+גרנט
* ✅ `/adm_recent save` — לוודא לוגים
* ✅ `/adm_setwebhook` — לוודא קישור webhook
* ✅ `/ping` — לוודא פעילות

---

## 🌐 שיתוף והפצה

שלח לחברים את ההודעה הבאה:

> **היי! 🚀**
>
> הרמנו בוט ניסוי על רשת BSC Testnet שמנפיק לכם NFT ונותן SELA.
>
> מה עושים?
>
> 1. ודאו שיש לכם רשת BSC Testnet בארנק (MetaMask).
> 2. שלחו לבוט:
>
> ```
> /mint <כתובת־הארנק שלכם>
> ```
>
> לדוגמה:
>
> ```
> /mint 0x693db6c817083818696a7228aEbfBd0Cd3371f02
> ```
>
> תקבלו קישורים ל־BscScan לעסקאות ה־Mint וה־SELA.
> אם משהו לא עובד — כתבו לנו בפרטי. תהנו! 🎉

---

© 2025 SLH Labs. כל הזכויות שמורות.

```

---

רוצה שאצור לך גם **תיקיית `/docs`** עם גרסה HTML יפה של ה־README (לפרסום בלינק או שליחה)?  
אם כן — אני יכול להוסיף קובץ `docs/index.html` עם גרסה רספונסיבית שתוכל להעלות ל־Vercel או Netlify בלחיצה אחת.
```
