import sqlite3
import re
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    ContextTypes, ConversationHandler, filters
)

BOT_TOKEN = "ضع_توكن_البوت_هنا"
DB_NAME = "jobs_database.db"

# مراحل إعداد الملف الشخصي
SET_SPECIALTY, SET_LOCATION = range(2)

# قائمة كلمات الحشو وحروف الجر لتجاهلها أثناء البحث
STOP_WORDS = {"في", "عن", "على", "من", "إلى", "بواسطة", "مع", "أو", "و", "فيها", "التي", "الذي", "اريد", "أريد", "ابحث", "أبحث"}

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- إعداد جداول قاعدة البيانات ---
def init_bot_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جدول ملفات المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            specialty TEXT,
            location TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# --- دالة البحث الذكي ---
def smart_search_jobs(query_text):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. تنظيف النص وتقطيعه لكرات مفتاحية حقيقية
    words = re.findall(r'\w+', query_text.lower())
    clean_keywords = [w for w in words if w not in STOP_WORDS and len(w) > 1]

    if not clean_keywords:
        conn.close()
        return []

    # 2. بناء استعلام SQL مرن يطابق الشروط بدون تزمت
    conditions = []
    params = []

    for word in clean_keywords:
        pattern = f"%{word}%"
        cond = "(job_title LIKE ? OR location LIKE ? OR requirements LIKE ? OR company LIKE ?)"
        conditions.append(cond)
        params.extend([pattern, pattern, pattern, pattern])

    # نستخدم AND بين الكلمات الأساسية
    sql_query = f"""
        SELECT job_title, company, location, requirements, contact, channel, created_at
        FROM jobs
        WHERE {' AND '.join(conditions)}
        ORDER BY id DESC
        LIMIT 10
    """

    cursor.execute(sql_query, params)
    results = cursor.fetchall()
    
    # إذا لم يجد نتائج بـ AND، نجرب البحث بـ OR لتوفير خيارات مقترحة
    if not results and len(clean_keywords) > 1:
        sql_query_or = f"""
            SELECT job_title, company, location, requirements, contact, channel, created_at
            FROM jobs
            WHERE {' OR '.join(conditions)}
            ORDER BY id DESC
            LIMIT 10
        """
        cursor.execute(sql_query_or, params)
        results = cursor.fetchall()

    conn.close()
    return results

# --- لوحة الأزرار الرئيسية ---
def main_keyboard():
    keyboard = [
        [KeyboardButton("🎯 وظائف تناسبني"), KeyboardButton("⚙️ إعداد ملفي الوظيفي")],
        [KeyboardButton("ℹ️ المساعدة")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- أمر /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_bot_db()
    welcome_text = (
        "مرحباً بك في بوت التوظيف الذكي! 💼\n\n"
        "• يمكنك **البحث مباشرة** بكتابة ما تريد (مثال: `كاشير في بغداد` أو `مصمم اربيل`).\n"
        "• أو اضغط **⚙️ إعداد ملفي الوظيفي** لتحديد تخصصك ومحافظتك ليجلب لك البوت الوظائف المناسبة بنقرة زر!"
    )
    await update.message.reply_text(welcome_text, reply_markup=main_keyboard(), parse_mode="Markdown")

# --- معالجة إعداد الملف الشخصي ---
async def start_profile_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ما هو تخصصك أو مجال عملك؟ (مثال: `كاشير`, `محاسب`, `تكنولوجيا معلومات`, `مبيعات`):"
    )
    return SET_SPECIALTY

async def save_specialty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['specialty'] = update.message.text.strip()
    await update.message.reply_text(
        "في أي محافظة أو منطقة تبحث عن عمل؟ (مثال: `بغداد`, `الكرخ`, `البصرة`, `اربيل`):"
    )
    return SET_LOCATION

async def save_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    specialty = context.user_data.get('specialty')
    location = update.message.text.strip()

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_profiles (user_id, specialty, location)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            specialty=excluded.specialty,
            location=excluded.location,
            updated_at=CURRENT_TIMESTAMP
    ''', (user_id, specialty, location))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ تم حفظ ملفك بنجاح!\n\n🎯 **التخصص:** {specialty}\n📍 **الموقع:** {location}\n\n"
        "الآن يمكنك اضغط على زر **🎯 وظائف تناسبني** في أي وقت لعرض أحدث الوظائف المطابقة!",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.", reply_markup=main_keyboard())
    return ConversationHandler.END

# --- معالجة زر "وظائف تناسبني" ---
async def get_matching_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT specialty, location FROM user_profiles WHERE user_id = ?", (user_id,))
    profile = cursor.fetchone()
    conn.close()

    if not profile:
        await update.message.reply_text(
            "لم تقم بإعداد ملفك الوظيفي بعد! اضغط على زر **⚙️ إعداد ملفي الوظيفي** أولاً.",
            parse_mode="Markdown"
        )
        return

    specialty, location = profile
    search_query = f"{specialty} {location}"
    await update.message.reply_text(f"🔍 جاري البحث عن وظائف تطابق ملفك: ({specialty} - {location})...")
    await display_results(update, search_query)

# --- معالجة البحث النصي العادي ---
async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🎯 وظائف تناسبني":
        await get_matching_jobs(update, context)
    elif text == "ℹ️ المساعدة":
        await start(update, context)
    else:
        await display_results(update, text)

# --- دالة عرض النتائج ---
async def display_results(update: Update, query_text: str):
    results = smart_search_jobs(query_text)

    if not results:
        await update.message.reply_text(
            f"❌ لم نجد وظائف مطابقة تماماً لـ: *{query_text}*\n"
            "جرّب البحث بكلمة مفتاحية واحدة مثل اسم المهنة فقط.",
            parse_mode="Markdown"
        )
        return

    response_msg = f"📋 **أحدث الوظائف المتاحة:**\n───────────────────\n\n"
    for idx, job in enumerate(results, start=1):
        job_title, company, location, requirements, contact, channel, created_at = job
        response_msg += f"🔹 **{idx}. {job_title}**\n"
        response_msg += f"🏢 **الجهة:** {company}\n"
        response_msg += f"📍 **الموقع:** {location}\n"
        if requirements and requirements != 'غير محدد':
            response_msg += f"📝 **الشروط:** {requirements}\n"
        response_msg += f"📞 **التواصل:** {contact}\n"
        response_msg += f"📢 **المصدر:** {channel}\n"
        response_msg += f"⏰ **التاريخ:** {created_at[:16]}\n"
        response_msg += "\n───────────────\n\n"

    if len(response_msg) > 4000:
        for x in range(0, len(response_msg), 4000):
            await update.message.reply_text(response_msg[x:x+4000], parse_mode="Markdown")
    else:
        await update.message.reply_text(response_msg, parse_mode="Markdown")

# --- تشغيل التطبيق ---
if __name__ == '__main__':
    init_bot_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # معالج إعداد الملف الشخصي (محادثة من خطوتين)
    profile_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^⚙️ إعداد ملفي الوظيفي$'), start_profile_setup)],
        states={
            SET_SPECIALTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_specialty)],
            SET_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_location)],
        },
        fallbacks=[CommandHandler('cancel', cancel_setup)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(profile_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))

    print("البوت الذكي يعمل بنجاح مع دعم الملفات الشخصية وتجاوز حروف الجر...")
    app.run_polling()
