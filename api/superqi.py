import json
from http.server import BaseHTTPRequestHandler

from services.webhook_server import process_successful_payment


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            status = payload.get("status")
            order_id = payload.get("orderId")
            if status not in {"SUCCESS", "PAID", "COMPLETED"} or not order_id:
                self.send_response(400)
                self.end_headers()
                return
            process_successful_payment(order_id)
            body = b'{"status":"SUCCESS"}'
            self.send_response(200)
        except Exception as error:
            print(f"SuperQi webhook failed: {error}")
            body = b'{"status":"FAILED"}'
            self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
