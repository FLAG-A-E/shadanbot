import json
import os
from http.server import BaseHTTPRequestHandler

from database.db import init_db
from services.cron_engine import hourly_job_sync


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        expected = os.getenv("CRON_SECRET", "")
        authorization = self.headers.get("Authorization", "")
        if expected and authorization != f"Bearer {expected}":
            self.send_response(401)
            self.end_headers()
            return

        try:
            init_db()
            hourly_job_sync()
            body = json.dumps({"ok": True}).encode()
            status = 200
        except Exception as error:
            print(f"Scheduled sync failed: {error}")
            body = json.dumps({"ok": False}).encode()
            status = 500

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
