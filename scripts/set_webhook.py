import os
import re

import requests


token = os.environ["SHADAN_BOT_TOKEN"]
base_url = os.environ["VERCEL_PROJECT_URL"].rstrip("/")
secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
if not base_url.startswith("https://"):
    raise SystemExit("VERCEL_PROJECT_URL يجب أن يبدأ بـ https://")
if secret and not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secret):
    raise SystemExit("TELEGRAM_WEBHOOK_SECRET يجب أن يحتوي فقط على A-Z a-z 0-9 _ -")
payload = {"url": f"{base_url}/api/telegram"}
if secret:
    payload["secret_token"] = secret

response = requests.post(
    f"https://api.telegram.org/bot{token}/setWebhook",
    json=payload,
    timeout=30,
)
result = response.json()
if not result.get("ok"):
    raise SystemExit(f"Telegram رفض Webhook: {result.get('description', result)}")
print(result)