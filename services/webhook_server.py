import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Bot
from config import BOT_TOKEN, CHANNEL_USERNAME
from database.connection import get_connection
from database.db import init_db

app = Flask(__name__)

bot = Bot(token=BOT_TOKEN)
init_db()

def process_successful_payment(order_ref: str):
    """
    يفكك معرف الطلب وتفعيل الخدمة بناءً عليه
    الصيغة: orderType_orderId_userId
    """
    parts = order_ref.split('_')
    if len(parts) < 3:
        return

    order_type = '_'.join(parts[:-2])
    order_id = parts[-2]
    user_id = int(parts[-1])
    
    conn = get_connection()
    cursor = conn.cursor()

    pending = cursor.execute(
        "SELECT job_text, status, plan_type FROM pending_job_posts WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    if pending and pending[1] == "published":
        conn.close()
        return

    # 1. تفعيل الإشعارات الفورية (1,000 د.ع)
    if order_type == "alerts":
        cursor.execute(
            "UPDATE user_profiles SET is_subscribed_alerts = 1, "
            "alerts_expires_at = datetime('now', '+30 days') WHERE user_id = ?",
            (user_id,),
        )
        asyncio.run(bot.send_message(
            chat_id=user_id,
            text="🎉 **تم تأكيد الدفع عبر SuperQi بنجاح!**\n\nتم تفعيل خدمة الإشعارات الفورية للوظائف المطابقة لتخصصك."
        ))

    # 2. تسديد خدمات הـ CV والبروتفوليو
    elif order_type in ["cv", "portfolio"]:
        cursor.execute("UPDATE cv_requests SET status = 'paid' WHERE id = ?", (order_id,))
        asyncio.run(bot.send_message(
            chat_id=user_id,
            text=f"✅ **تم استلام مبلغ الخدمة بنجاح!**\n\nجاري إعداد الملف من قبل فريق شَدان وسيتم إرساله لك هنا فور تجهيزه."
        ))

    # 3. باقات أصحاب الأعمال (نشر الوظائف)
    elif order_type in ["jobmonthly", "job_monthly", "job_single"]:
        if not pending:
            conn.close()
            logging.error("لا يوجد إعلان مؤقت للطلب المدفوع %s", order_id)
            return

        job_text = pending[0]
        asyncio.run(bot.send_message(chat_id=CHANNEL_USERNAME, text=job_text))
        cursor.execute(
            "UPDATE pending_job_posts SET status = 'published', published_at = CURRENT_TIMESTAMP WHERE order_id = ?",
            (order_id,),
        )

        if order_type in ["jobmonthly", "job_monthly"]:
            # الإعلان الحالي يستهلك وظيفة واحدة، ويبقى 24 إعلانًا في الباقة.
            cursor.execute("""
                INSERT INTO employer_subscriptions (employer_id, plan_type, jobs_left, expires_at)
                VALUES (?, 'monthly', 24, datetime('now', '+30 days'))
                ON CONFLICT(employer_id) DO UPDATE SET
                    plan_type = 'monthly',
                    jobs_left = employer_subscriptions.jobs_left + 24,
                    expires_at = datetime('now', '+30 days')
            """, (user_id,))

        asyncio.run(bot.send_message(
            chat_id=user_id,
            text="✅ تم تأكيد الدفع ونشر إعلانك مباشرة في القناة. سيقوم السكرابر بفهرسته لاحقًا.",
        ))

    # التوافق مع الصيغة القديمة للطلبات الشهرية دون إعلان مرتبط
    elif order_type == "jobmonthly_legacy":
        cursor.execute("""
            INSERT INTO employer_subscriptions (employer_id, plan_type, jobs_left, expires_at)
            VALUES (?, 'monthly', 25, datetime('now', '+30 days'))
            ON CONFLICT(employer_id) DO UPDATE SET jobs_left = jobs_left + 25
        """, (user_id,))
        asyncio.run(bot.send_message(
            chat_id=user_id,
            text="🎉 **تم تفعيل اشتراك أصحاب الأعمال الشهرية!**\n\nلديك الآن رصيد 25 وظيفة يمكنك نشرها في أي وقت."
        ))

    conn.commit()
    conn.close()

@app.route('/webhook/superqi', methods=['POST'])
def superqi_webhook():
    data = request.json or {}
    
    # التأكد من رمز نجاح العملية المعتمد في سوبر كي
    if data.get("status") in ["SUCCESS", "PAID", "COMPLETED"]:
        order_ref = data.get("orderId")
        process_successful_payment(order_ref)
        return jsonify({"status": "SUCCESS"}), 200
        
    return jsonify({"status": "FAILED"}), 400

if __name__ == '__main__':
    # تشغيل خادم الويب هوك على المنفذ 5000
    app.run(host='0.0.0.0', port=5000)
