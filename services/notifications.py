import asyncio
import logging

from telegram import Bot

from config import BOT_TOKEN, DB_NAME
from database.connection import get_connection
from handlers.jobs import calculate_match_score
from services.gemini_matching import score_jobs_for_profile


def notify_subscribed_users(jobs):
    if not jobs or not BOT_TOKEN:
        return

    connection = get_connection()
    try:
        users = connection.execute(
            "SELECT user_id, full_name, gender, degree, department, job_title, possible_jobs, governorate, desired_salary "
            "FROM user_profiles "
            "WHERE is_subscribed_alerts = 1 "
            "AND (alerts_expires_at IS NULL OR alerts_expires_at > datetime('now'))"
        ).fetchall()
    finally:
        connection.close()

    if not users:
        return

    bot = Bot(token=BOT_TOKEN)
    for row in users:
        profile = {
            "full_name": row[1],
            "gender": row[2],
            "degree": row[3],
            "department": row[4],
            "job_title": row[5],
            "possible_jobs": row[6],
            "governorate": row[7],
            "desired_salary": row[8],
        }
        candidates = []
        for job in jobs:
            job_data = {
                "id": job.get("id", 0),
                "job_title": job.get("job_title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "requirements": job.get("requirements"),
                "contact_info": job.get("contact") or job.get("contact_info"),
                "raw_text": job.get("raw_text"),
            }
            if calculate_match_score(profile, job_data) >= 45:
                candidates.append(job_data)

        if not candidates:
            continue

        semantic_scores = score_jobs_for_profile(profile, candidates[:60])
        matching_jobs = []
        for job in candidates:
            ai_score = semantic_scores.get(job["id"]) if semantic_scores else None
            if ai_score is None:
                ai_score = calculate_match_score(profile, job)
            if ai_score >= 65:
                matching_jobs.append((ai_score, job))

        matching_jobs.sort(key=lambda item: item[0], reverse=True)

        if not matching_jobs:
            continue

        message = "🔔 وظائف جديدة تناسب ملفك الشخصي:\n\n"
        for score, job in matching_jobs[:5]:
            message += (
                f"📊 التطابق: {score}%\n"
                f"💼 {job['job_title'] or 'غير محدد'}\n"
                f"🏢 {job['company'] or 'غير معلن'}\n"
                f"📍 {job['location'] or 'غير محدد'}\n"
                f"📞 {job['contact_info'] or 'غير متوفر'}\n\n"
            )

        try:
            asyncio.run(bot.send_message(chat_id=row[0], text=message))
        except Exception as error:
            logging.warning("تعذر إرسال إشعار للمستخدم %s: %s", row[0], error)
