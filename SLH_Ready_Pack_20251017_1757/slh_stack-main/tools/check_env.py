import os, sys, re

REQUIRED = [
    "TELEGRAM_BOT_TOKEN",
    "SLH_API_BASE",
    "BOT_MODE",
]

errors = []
for k in REQUIRED:
    if not os.getenv(k):
        errors.append(f"Missing {k}")

pub = os.getenv("BOT_WEBHOOK_PUBLIC_BASE","")
secret = os.getenv("BOT_WEBHOOK_SECRET","")
mode = os.getenv("BOT_MODE","webhook").lower().strip()

if mode == "webhook":
    if not pub.startswith("https://"):
        errors.append("BOT_WEBHOOK_PUBLIC_BASE must start with https:// in webhook mode")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", secret or ""):
        errors.append("BOT_WEBHOOK_SECRET must be [A-Za-z0-9_-]+")

if errors:
    print("Env check FAILED:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
else:
    print("Env check OK.")
    print("API:", os.getenv("SLH_API_BASE"))
    print("Mode:", mode)
