import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler

from telegram import Update

from main import build_telegram_application


async def process_payload(payload):
    application = build_telegram_application()
    await application.initialize()
    await application.start()
    try:
        update = Update.de_json(payload, application.bot)
        await application.process_update(update)
    finally:
        await application.stop()
        await application.shutdown()


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
        received_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if expected_secret and received_secret != expected_secret:
            self.send_response(403)
            self.end_headers()
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            asyncio.run(process_payload(payload))
            response = {"ok": True}
            status = 200
        except Exception as error:
            print(f"Telegram webhook failed: {error}")
            response = {"ok": False}
            status = 500

        body = json.dumps(response).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = b'{"ok":true,"service":"telegram-webhook"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
