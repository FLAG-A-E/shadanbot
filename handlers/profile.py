import logging
import re
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
)

from config import DB_NAME
from database.connection import get_connection
from database.db import init_db
from ui import main_keyboard

# مراحل إعداد الملف الشخصي. الاسم يؤخذ من حساب تليكرام مباشرة.
PROFILE_ACTION, GENDER, DEGREE, DEPARTMENT, TITLE, POSSIBLE_JOBS, GOVERNORATE, SALARY = range(8)
BACK_TEXT = "↩️ عودة"

# --- قائمة المحافظات العراقية الخيارات السريعة ---
IRAQ_GOVERNORATES = [
    ["بغداد", "واسط"],
    ["البصرة", "أربيل", "النجف الأشرف"],
    ["كربلاء المقدسة", "بابل", "ذي قار"],
    ["الديوانية", "المثنى", "ميسان"],
    ["ديالى", "صلاح الدين", "كركوك"],
    ["نينوى", "الأنبار", "دهوك"],
    ["سليمانية", "كل المحافظات (عمل عن بُعد)"]
]

# --- إنشاء الجدول عند التشغيل ---
init_db()

def get_profile(user_id):
    conn = get_connection()
    profile = conn.execute(
        "SELECT full_name, gender, degree, department, job_title, possible_jobs, governorate, desired_salary "
        "FROM user_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return profile


def profile_summary(profile):
    return (
        "👤 **معلومات ملفك الشخصي**\n\n"
        f"**الاسم:** {profile[0] or 'غير محدد'}\n"
        f"**الجنس:** {profile[1] or 'غير محدد'}\n"
        f"**الشهادة:** {profile[2] or 'غير محدد'}\n"
        f"**التخصص:** {profile[3] or 'غير محدد'}\n"
        f"**المسمى الوظيفي:** {profile[4] or 'غير محدد'}\n"
        f"**المجالات المقبولة:** {profile[5] or 'غير محدد'}\n"
        f"**المحافظة:** {profile[6] or 'غير محدد'}\n\n"
        f"**الراتب المطلوب:** {profile[7] or 'غير محدد'}\n\n"
        "هل ترغب في تعديل معلوماتك؟"
    )


async def begin_profile_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data['full_name'] = user.full_name or user.username or str(user.id)

    gender_keyboard = [["ذكر 👨", "أنثى 👩"], [BACK_TEXT]]
    await update.message.reply_text(
        "📝 **إعداد الملف الشخصي - بوت شَدان**\n\n"
        "لتصلك الوظائف المطابقة تماماً لمهاراتك وتخصصك، يرجى إدخال معلوماتك بدقة.\n\n"
        f"سيتم استخدام اسم حسابك في تليكرام: **{context.user_data['full_name']}**\n\n"
        "**الخطوة 1 من 6:** اختر الجنس:",
        reply_markup=ReplyKeyboardMarkup(gender_keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return GENDER


# --- عرض الملف الحالي أو بدء الإعداد لأول مرة ---
async def start_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = get_profile(update.effective_user.id)
    if not profile or not profile[0]:
        return await begin_profile_setup(update, context)

    await update.message.reply_text(
        profile_summary(profile),
        reply_markup=ReplyKeyboardMarkup(
            [["✏️ تعديل الملف"], [BACK_TEXT]],
            one_time_keyboard=True,
            resize_keyboard=True,
        ),
        parse_mode="Markdown",
    )
    return PROFILE_ACTION


async def profile_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == "✏️ تعديل الملف":
        return await begin_profile_setup(update, context)
    return await cancel_profile(update, context)

# --- الخطوة 1: الجنس ---
async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gender_text = update.message.text.strip()
    context.user_data['gender'] = "ذكر" if "ذكر" in gender_text else "أنثى"
    
    degree_keyboard = [
        ["إعدادية فما دون", "دبلوم"],
        ["بكالوريوس", "ماجستير / دكتوراه"],
        ["طالب جامعي / شهادة مهنية"],
        [BACK_TEXT]
    ]
    await update.message.reply_text(
        "**الخطوة 2 من 6:** حدد المستوى العلمي / الشهادة:",
        reply_markup=ReplyKeyboardMarkup(degree_keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return DEGREE

# --- الخطوة 2: الشهادة ---
async def set_degree(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['degree'] = update.message.text.strip()
    
    await update.message.reply_text(
        "**الخطوة 3 من 6:** اكتب اسم التخصص / القسم الدقيق:\n"
        "*(مثال: تقنيات تحليلات مرضية، علوم حاسوب، هندسة مدني، إدارة أعمال)*",
        reply_markup=ReplyKeyboardMarkup([[BACK_TEXT]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return DEPARTMENT

# --- الخطوة 3: القسم / التخصص ---
async def set_department(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['department'] = update.message.text.strip()
    
    await update.message.reply_text(
        "**الخطوة 4 من 6:** ما هو المسمى الوظيفي المستهدف أو صفة عملك الحالية؟\n"
        "*(مثال: مبرمج ويب، محلل مختبر، كاتب محتوى، محاسب، موظف مبيعات)*",
        reply_markup=ReplyKeyboardMarkup([[BACK_TEXT]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return TITLE

# --- الخطوة 4: المسمى الوظيفي ---
async def set_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['job_title'] = update.message.text.strip()
    
    await update.message.reply_text(
        "**الخطوة 5 من 6:** اكتب جميع الوظائف والمجالات التي يمكنك أو ترغب بالعمل بها (افصل بينها بفارزة):\n"
        "*(مثال: إدخال بيانات، تسويق إلكتروني، إدارة صفحات، خدمة عملاء)*",
        reply_markup=ReplyKeyboardMarkup([[BACK_TEXT]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return POSSIBLE_JOBS

# --- الخطوة 5: الوظائف الممكنة ---
async def set_possible_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['possible_jobs'] = update.message.text.strip()
    
    await update.message.reply_text(
        "**الخطوة 6 من 7:** حدد المحافظة التي تبحث فيها عن عمل:",
        reply_markup=ReplyKeyboardMarkup(IRAQ_GOVERNORATES + [[BACK_TEXT]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return GOVERNORATE

# --- الخطوة 6: المحافظة وحفظ البيانات ---
async def set_governorate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gov = update.message.text.strip()
    if gov.startswith("واسط"):
        gov = "واسط"
    context.user_data['governorate'] = gov
    await update.message.reply_text(
        "**الخطوة 7 من 7:** ما الراتب الشهري الأدنى الذي تقبله؟\n"
        "اكتب المبلغ بالدينار، أو اكتب **غير محدد** إذا لم يكن شرطاً.",
        reply_markup=ReplyKeyboardMarkup([[BACK_TEXT]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return SALARY


async def set_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    salary = update.message.text.strip()
    if len(salary) > 100:
        await update.message.reply_text("اكتب الراتب بشكل مختصر، مثل: 800000 أو غير محدد.")
        return SALARY
    context.user_data['desired_salary'] = salary
    
    # حفظ في قاعدة البيانات SQLite
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_profiles 
        (user_id, full_name, gender, degree, department, job_title, possible_jobs, governorate, desired_salary, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            full_name=excluded.full_name,
            gender=excluded.gender,
            degree=excluded.degree,
            department=excluded.department,
            job_title=excluded.job_title,
            possible_jobs=excluded.possible_jobs,
            governorate=excluded.governorate,
            desired_salary=excluded.desired_salary,
            updated_at=CURRENT_TIMESTAMP
    ''', (
        user_id,
        context.user_data['full_name'],
        context.user_data['gender'],
        context.user_data['degree'],
        context.user_data['department'],
        context.user_data['job_title'],
        context.user_data['possible_jobs'],
        context.user_data['governorate'],
        context.user_data['desired_salary']
    ))
    conn.commit()
    conn.close()

    summary_text = (
        "🎉 **تم إكمال ملفك الشخصي في شَدان بنجاح!**\n\n"
        f"👤 **الاسم:** {context.user_data['full_name']} ({context.user_data['gender']})\n"
        f"🎓 **الشهادة والتخصص:** {context.user_data['degree']} - {context.user_data['department']}\n"
        f"💼 **المسمى الوظيفي:** {context.user_data['job_title']}\n"
        f"🛠️ **المجالات المقبولة:** {context.user_data['possible_jobs']}\n"
        f"📍 **المحافظة:** {context.user_data['governorate']}\n\n"
        f"💰 **الراتب المطلوب:** {context.user_data['desired_salary']}\n\n"
        "💡 *يمكنك الآن الضغط على (🎯 وظائف تناسبني) لعرض الفرص المتطابقة مع ملفك فوراً.*"
    )

    await update.message.reply_text(
        summary_text, 
        reply_markup=main_keyboard(), 
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# --- الإلغاء ---
async def cancel_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "تم الرجوع للقائمة الرئيسية.", 
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END

# --- إعداد الهاندلر للتصدير إلى الكود الرئيسي ---
profile_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex('^(👤 ملفي الشخصي|/profile)$'), start_profile)
    ],
    states={
        PROFILE_ACTION: [
            MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_profile),
            MessageHandler(filters.Regex(r'^✏️ تعديل الملف$'), profile_action),
        ],
        GENDER: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_profile), MessageHandler(filters.TEXT & ~filters.COMMAND, set_gender)],
        DEGREE: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_profile), MessageHandler(filters.TEXT & ~filters.COMMAND, set_degree)],
        DEPARTMENT: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_profile), MessageHandler(filters.TEXT & ~filters.COMMAND, set_department)],
        TITLE: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_profile), MessageHandler(filters.TEXT & ~filters.COMMAND, set_title)],
        POSSIBLE_JOBS: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_profile), MessageHandler(filters.TEXT & ~filters.COMMAND, set_possible_jobs)],
        GOVERNORATE: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_profile), MessageHandler(filters.TEXT & ~filters.COMMAND, set_governorate)],
        SALARY: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_profile), MessageHandler(filters.TEXT & ~filters.COMMAND, set_salary)],
    },
    fallbacks=[CommandHandler('cancel', cancel_profile)]
)
