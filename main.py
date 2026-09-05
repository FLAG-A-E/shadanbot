import asyncio
import logging
import os
import threading

from flask import Flask, jsonify, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from config import BOT_TOKEN, PUBLIC_BASE_URL
from database.db import init_db
from handlers.employers import employer_conv_handler, payment_decision
from handlers.jobs import (
    alert_payment_conv_handler,
    alert_payment_decision,
    job_search_conv_handler,
    matched_jobs_handler,
)
from handlers.profile import profile_conv_handler
from handlers.services import services_conv_handler
from services.subscription_gate import check_subscription, subscription_gate
from ui import BACK_TEXT, main_keyboard


app = Flask(__name__)
telegram_app = None
telegram_loop = None
services_started = False


async def start(update, context):
    await update.message.reply_text(
        "أهلاً بك في **شَدان** 💼✨\nمنصتك الذكية للوظائف والخدمات المهنية.",
        reply_markup=main_keyboard(),
        parse_mode="Markdown",
    )


async def back_to_main(update, context):
    await update.message.reply_text("تم الرجوع للقائمة الرئيسية.", reply_markup=main_keyboard())


def build_telegram_application():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(TypeHandler(Update, subscription_gate), group=-1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(profile_conv_handler)
    application.add_handler(services_conv_handler)
    application.add_handler(employer_conv_handler)
    application.add_handler(CallbackQueryHandler(payment_decision, pattern=r"^(approve_job|reject_job):"))
    application.add_handler(CallbackQueryHandler(alert_payment_decision, pattern=r"^(approve_alert|reject_alert):"))
    application.add_handler(CallbackQueryHandler(check_subscription, pattern=r"^check_subscription$"))
    application.add_handler(job_search_conv_handler)
    application.add_handler(MessageHandler(filters.Regex("^🎯 وظائف تناسبني$"), matched_jobs_handler))
    application.add_handler(alert_payment_conv_handler)
    application.add_handler(MessageHandler(filters.Regex(f"^{BACK_TEXT}$"), back_to_main))
    return application


async def initialize_telegram():
    await telegram_app.initialize()
    await telegram_app.start()
    public_url = PUBLIC_BASE_URL.rstrip("/")
    if not public_url.endswith("your-domain.com"):
        await telegram_app.bot.set_webhook(url=f"{public_url}/api/telegram")
        logging.info("Telegram webhook configured at %s/api/telegram", public_url)
    else:
        logging.warning("SHADAN_PUBLIC_BASE_URL أو RENDER_EXTERNAL_URL غير مضبوط")


def telegram_worker():
    global telegram_loop
    telegram_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(telegram_loop)
    telegram_loop.run_until_complete(initialize_telegram())
    telegram_loop.run_forever()


@app.get("/")
def health_check():
    return jsonify({"status": "ok", "service": "shadan-bot"})


@app.post("/telegram/webhook")
def telegram_webhook():
    if telegram_app is None or telegram_loop is None:
        return jsonify({"status": "starting"}), 503
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"status": "invalid payload"}), 400
    update = Update.de_json(payload, telegram_app.bot)
    asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), telegram_loop)
    return jsonify({"status": "accepted"}), 200


@app.post("/webhook/superqi")
def superqi_webhook():
    from services.webhook_server import process_successful_payment

    data = request.get_json(silent=True) or {}
    if data.get("status") not in {"SUCCESS", "PAID", "COMPLETED"}:
        return jsonify({"status": "FAILED"}), 400
    process_successful_payment(data.get("orderId", ""))
    return jsonify({"status": "SUCCESS"}), 200


def run():
    start_services()
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)


def start_services():
    global telegram_app, services_started
    if services_started:
        return
    logging.basicConfig(level=logging.INFO)
    init_db()
    if not BOT_TOKEN or BOT_TOKEN == "ضع_توكن_البوت_هنا":
        raise RuntimeError("ضع SHADAN_BOT_TOKEN في متغيرات البيئة.")
    telegram_app = build_telegram_application()
    threading.Thread(target=telegram_worker, daemon=True).start()
    services_started = True


if __name__ == "__main__":
    run()
