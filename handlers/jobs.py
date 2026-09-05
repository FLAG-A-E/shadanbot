import logging
import re
import uuid
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from config import ADMIN_GROUP_ID, ADMIN_ID, DB_NAME
from database.connection import get_connection
from services.gemini_matching import score_jobs_for_profile, score_jobs_for_search
from ui import BACK_TEXT, back_keyboard, main_keyboard

SEARCH_QUERY = 1
SEARCH_AGAIN_TEXT = "🔁 بحث مرة أخرى"

STOP_WORDS = {
    "في", "من", "عن", "على", "الى", "إلى", "و", "او", "أو", "اريد", "أريد",
    "ابحث", "أبحث", "وظيفة", "وظائف", "عمل", "شغل", "فرصة", "فرص"
}

JOB_SYNONYMS = {
    "كاشير": {"كاشير", "كاشير", "كاشيره", "كاشيرة", "cashier", "صندوق", "محاسب صندوق"},
    "محاسب": {"محاسب", "محاسبه", "محاسبة", "accountant"},
    "مبيعات": {"مبيعات", "مندوب", "مندوبه", "بائع", "بائعه", "سيلز", "sales"},
    "سائق": {"سائق", "سايق", "دليفري", "توصيل", "driver"},
}

LOCATION_WORDS = {
    "العراق", "بغداد", "الكرخ", "الرصافه", "الرصافة", "البصره", "البصرة",
    "اربيل", "أربيل", "هولير", "النجف", "كربلاء", "بابل", "واسط", "الكوت",
    "السويره", "السويرة", "الشويره", "الشويرة", "ذي", "قار", "ذيقار",
    "الديوانيه", "الديوانية", "المثنى", "ميسان", "ديالى", "صلاح", "الدين",
    "كركوك", "نينوى", "الموصل", "الانبار", "الأنبار", "دهوك", "السليمانيه",
    "سليمانية", "السليمانية", "عن", "بعد"
}

MEDICAL_CONTEXT_WORDS = {
    "طبي", "طبيه", "مرض", "مرضي", "مرضيه", "تحاليل مرضيه", "مختبر طبي",
    "مختبرات طبيه", "مستشفي", "مستشفى", "سريري", "احياء", "كيمياء سريريه",
}
ENVIRONMENTAL_CONTEXT_WORDS = {
    "بيئي", "بيئه", "تربه", "زراعه", "زراعي", "مياه", "اغذيه", "اغذائي",
    "نبات", "نباتات", "جيولوجيا", "نفط", "معادن", "صرف صحي",
}

# --- دالة جلب الملف الشخصي للمستخدم ---
def get_user_profile(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT full_name, gender, degree, department, job_title, possible_jobs, governorate, desired_salary
        FROM user_profiles WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "full_name": row[0],
            "gender": row[1],
            "degree": row[2],
            "department": row[3],
            "job_title": row[4],
            "possible_jobs": row[5],
            "governorate": row[6],
            "desired_salary": row[7],
        }
    return None

# --- دالة حساب درجة المطابقة الذكية بين الملف والوظيفة ---
def calculate_match_score(profile, job):
    """
    تحسب درجة ملاءمة الوظيفة للمستخدم (من 0 إلى 100)
    """
    score = 0
    job_title = normalize_text(job.get('job_title'))
    job_desc = normalize_text((job.get('requirements') or "") + " " + (job.get('raw_text') or ""))
    job_loc = normalize_text(job.get('location'))
    searchable_text = f"{job_title} {job_desc}"

    if has_domain_conflict(
        " ".join(str(value or "") for value in profile.values()),
        searchable_text,
    ):
        return 0

    # 1. مطابقة المحافظة (30 نقطة)
    user_gov = normalize_text(profile.get('governorate'))
    location_matches = (
        not user_gov
        or user_gov in job_loc
        or "كل المحافظات" in job_loc
        or "عمل عن بعد" in job_loc
        or "عن بعد" in job_loc
    )
    if location_matches:
        score += 30
    elif "واسط" in user_gov and ("الكوت" in job_loc or "الشويرة" in job_loc or "السويرة" in job_loc):
        score += 30

    # 2. مطابقة التخصص والمسمى الوظيفي (40 نقطة)
    dept = normalize_text(profile.get('department'))
    title = normalize_text(profile.get('job_title'))
    
    if dept and (dept in job_title or dept in job_desc):
        score += 15
    if title:
        title_terms = expand_job_keywords(extract_keywords(title))
        if any(term in job_title for term in title_terms):
            score += 25
        elif any(term in searchable_text for term in title_terms):
            score += 15

    # 3. مطابقة الوظائف الممكنة والمهارات (30 نقطة)
    possible_jobs = [
        normalize_text(j.strip())
        for j in re.split(r"[,،\n]+", profile.get('possible_jobs') or "")
        if j.strip()
    ]
    for job_item in possible_jobs:
        possible_terms = expand_job_keywords(extract_keywords(job_item)) or {job_item}
        if job_item in job_title or any(term in job_title for term in possible_terms):
            score += 35
            break
        if job_item in job_desc or any(term in job_desc for term in possible_terms):
            score += 22
            break

    if not location_matches:
        return min(score, 35)
    return min(score, 100)


def normalize_text(text):
    text = (text or "").lower()
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def has_domain_conflict(profile_text, job_text):
    profile_text = normalize_text(profile_text)
    job_text = normalize_text(job_text)
    has_medical_context = any(term in profile_text for term in MEDICAL_CONTEXT_WORDS)
    has_environmental_context = any(term in job_text for term in ENVIRONMENTAL_CONTEXT_WORDS)
    return has_medical_context and has_environmental_context


def extract_keywords(text):
    words = re.findall(r"[\w\u0600-\u06FF]+", normalize_text(text))
    return [word for word in words if len(word) > 1 and word not in STOP_WORDS]


def job_action_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(SEARCH_AGAIN_TEXT), KeyboardButton(BACK_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def split_search_intent(keywords):
    location_keywords = [word for word in keywords if word in {normalize_text(w) for w in LOCATION_WORDS}]
    job_keywords = [word for word in keywords if word not in location_keywords]
    return job_keywords, location_keywords


def expand_job_keywords(keywords):
    expanded = set(keywords)
    for keyword in keywords:
        for canonical, synonyms in JOB_SYNONYMS.items():
            normalized_synonyms = {normalize_text(item) for item in synonyms}
            if keyword == normalize_text(canonical) or keyword in normalized_synonyms:
                expanded.update(normalized_synonyms)
    return expanded


def calculate_search_score(keywords, job):
    searchable_parts = [
        job.get("job_title"),
        job.get("company"),
        job.get("location"),
        job.get("requirements"),
        job.get("contact_info"),
        job.get("raw_text"),
    ]
    searchable_text = normalize_text(" ".join(part or "" for part in searchable_parts))
    title_text = normalize_text(job.get("job_title"))
    location_text = normalize_text(job.get("location"))

    if has_domain_conflict(" ".join(keywords), searchable_text):
        return 0

    job_keywords, location_keywords = split_search_intent(keywords)
    expanded_job_keywords = expand_job_keywords(job_keywords)

    if job_keywords and not any(keyword in title_text or keyword in searchable_text for keyword in expanded_job_keywords):
        return 0

    score = 0
    for keyword in expanded_job_keywords:
        if keyword in title_text:
            score += 45
        elif keyword in searchable_text:
            score += 22

    for keyword in location_keywords:
        if keyword in location_text:
            score += 30
        elif keyword in searchable_text:
            score += 10

    if job_keywords and location_keywords:
        has_job_match = any(keyword in title_text or keyword in searchable_text for keyword in expanded_job_keywords)
        has_location_match = any(keyword in location_text or keyword in searchable_text for keyword in location_keywords)
        if not (has_job_match and has_location_match):
            return 0

    return min(score, 100)


def smart_search_jobs(query_text, limit=10):
    keywords = extract_keywords(query_text)
    if not keywords:
        return []

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, job_title, company, location, requirements, contact_info, raw_text
        FROM jobs
        ORDER BY id DESC
        LIMIT 200
    """)
    rows = cursor.fetchall()
    conn.close()

    scored_jobs = []
    all_jobs = []
    for row in rows:
        job = {
            "id": row[0],
            "job_title": row[1],
            "company": row[2],
            "location": row[3],
            "requirements": row[4],
            "contact_info": row[5],
            "raw_text": row[6],
        }
        all_jobs.append(job)
        score = calculate_search_score(keywords, job)
        if score:
            scored_jobs.append((score, job))

    # إذا لم يلتقط البحث المحلي مرشحًا، نرسل أحدث الوظائف إلى Gemini لفهم المعنى.
    candidates = [job for _, job in scored_jobs] or all_jobs[:80]
    semantic_scores = score_jobs_for_search(query_text, candidates)
    if semantic_scores:
        scored_jobs = [
            (details["score"], job)
            for job in candidates
            if (details := semantic_scores.get(job["id"]))
            and details["relevant"]
            and details["score"] >= 45
        ]

    scored_jobs.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
    return scored_jobs[:limit]


async def send_job_results(update: Update, scored_jobs, empty_message):
    if not scored_jobs:
        await update.message.reply_text(empty_message, parse_mode="Markdown", reply_markup=job_action_keyboard())
        return

    await update.message.reply_text(
        f"🔍 **وجدت {len(scored_jobs)} نتيجة مناسبة لبحثك:**\n" + "─" * 25,
        parse_mode="Markdown"
    )
    for score, job in scored_jobs:
        details = job.get("requirements") or job.get("raw_text") or "لا توجد تفاصيل إضافية"
        msg = (
            f"📊 **قوة التطابق: {score}%**\n"
            f"💼 **الوظيفة:** {job.get('job_title') or 'عامة'}\n"
            f"🏢 **الشركة:** {job.get('company') or 'غير معلن'}\n"
            f"📍 **المكان:** {job.get('location') or 'العراق'}\n"
            f"📝 **التفاصيل:** {details[:700]}\n"
            f"📞 **التواصل:** {job.get('contact_info') or 'غير متوفر'}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    await update.message.reply_text("اختر الخطوة التالية:", reply_markup=job_action_keyboard())

# --- 🎯 معالج زر: "وظائف تناسبني" (المطابقة الذكية) ---
async def matched_jobs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)

    # إذا لم يكن للمستخدم ملف شخصي
    if not profile:
        await update.message.reply_text(
            "⚠️ **لم تقم بإنشاء ملفك الشخصي بعد!**\n\n"
            "يرجى الضغط على زر **(👤 ملفي الشخصي)** أولاً لندخل تخصصك ومحافظتك ونطابق الوظائف المناسبة لك.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return

    await update.message.reply_text(
        "🔍 جارٍ البحث وتحليل الوظائف المناسبة لملفك...\n"
        "قد يستغرق التحليل بضع ثوانٍ.",
    )

    # جلب جميع الوظائف المخزنة من قاعدة البيانات
    conn = get_connection()
    cursor = conn.cursor()
    # تنويه: يتوقع وجود جدول jobs بالحقول التالية
    cursor.execute("SELECT id, job_title, company, location, requirements, contact_info, raw_text FROM jobs ORDER BY id DESC LIMIT 50")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 لا توجد وظائف مسجلة في النظام حالياً. يرجى المحاولة لاحقاً!", reply_markup=job_action_keyboard())
        return

    # حساب الدرجات ورص الوظائف المطابقة
    scored_jobs = []
    all_jobs = []
    for r in rows:
        job_data = {
            "id": r[0], "job_title": r[1], "company": r[2], 
            "location": r[3], "requirements": r[4], "contact_info": r[5], "raw_text": r[6]
        }
        all_jobs.append(job_data)
        score = calculate_match_score(profile, job_data)
        if score >= 25:
            scored_jobs.append((score, job_data))

    candidates = [job for _, job in scored_jobs] or all_jobs
    gemini_scores = score_jobs_for_profile(profile, candidates)
    if gemini_scores:
        scored_jobs = [
            (details, job)
            for job in candidates
            if (details := gemini_scores.get(job["id"])) is not None
            and details >= 45
        ]

    # ترتيب الوظائف من الأكثر مطابقة للأقل
    scored_jobs.sort(key=lambda x: (x[0], x[1]["id"]), reverse=True)

    if not scored_jobs:
        await update.message.reply_text(
            f"🔍 لم نجد وظائف مطابقة تماماً لتخصصك (**{profile['department']}**) في محافظة (**{profile['governorate']}**) حالياً.\n\n"
            "💡 يمكنك الاستعانة بزر **(🔍 بحث عن وظيفة)** للبحث العام.",
            parse_mode="Markdown",
            reply_markup=job_action_keyboard()
        )
        return

    await update.message.reply_text(f"🎯 **وجدنا {len(scored_jobs[:5])} وظائف تناسب ملفك الشخصي:**\n"+"─"*25, parse_mode="Markdown")

    # عرض أعلى 5 وظائف مطابقة
    for score, job in scored_jobs[:5]:
        msg = (
            f"📊 **نسبة المطابقة: {score}%**\n"
            f"💼 **الوظيفة:** {job['job_title'] or 'غير محدد'}\n"
            f"🏢 **الجهة/الشركة:** {job['company'] or 'غير محدد'}\n"
            f"📍 **الموقع:** {job['location'] or 'غير محدد'}\n\n"
            f"📝 **المتطلبات/التفاصيل:**\n{job['requirements'] or job['raw_text'][:200]}\n\n"
            f"📞 **التواصل:** {job['contact_info'] or 'راجع الإعلان'}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    await update.message.reply_text("اختر الخطوة التالية:", reply_markup=job_action_keyboard())

# --- 🔍 معالج زر: "بحث عن وظيفة" ---
async def latest_jobs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 اكتب الوظيفة أو المجال أو المحافظة التي تبحث عنها.\n"
        "مثال: `محاسب بغداد` أو `مختبر واسط` أو `مبيعات اربيل`",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(BACK_TEXT)]], resize_keyboard=True, one_time_keyboard=True),
        parse_mode="Markdown"
    )
    return SEARCH_QUERY


async def handle_job_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()

    if query in {"الغاء", "إلغاء", "/cancel", BACK_TEXT}:
        await update.message.reply_text("تم الرجوع للقائمة الرئيسية.", reply_markup=main_keyboard())
        return ConversationHandler.END

    if query in {SEARCH_AGAIN_TEXT, "🔍 بحث عن وظيفة"}:
        return await latest_jobs_handler(update, context)

    if query == "🎯 وظائف تناسبني":
        await matched_jobs_handler(update, context)
        return ConversationHandler.END

    if normalize_text(query) in {"احدث", "اخر الوظائف", "الوظائف الاخيره"}:
        await send_latest_jobs(update)
        return ConversationHandler.END

    await update.message.reply_text(
        "🔍 جارٍ البحث وتحليل النتائج...\n"
        "سأتحقق من المجال والخبرة وليس تطابق الكلمات فقط.",
    )
    results = smart_search_jobs(query)
    await send_job_results(
        update,
        results,
        f"❌ لم أجد وظائف تطابق بحثك: **{query}**\nجرّب كلمة أبسط مثل: `محاسب` أو اسم المحافظة فقط."
    )
    return ConversationHandler.END


async def cancel_job_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء البحث.", reply_markup=main_keyboard())
    return ConversationHandler.END


async def send_latest_jobs(update: Update):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT job_title, company, location, requirements, contact_info FROM jobs ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📭 لا توجد وظائف مضافة حالياً.", reply_markup=job_action_keyboard())
        return

    await update.message.reply_text("🔍 **أحدث الوظائف المضافة مؤخراً في شَدان:**\n"+"─"*25, parse_mode="Markdown")
    for r in rows:
        msg = (
            f"💼 **الوظيفة:** {r[0] or 'عامة'}\n"
            f"🏢 **الشركة:** {r[1] or 'غير معلن'}\n"
            f"📍 **المكان:** {r[2] or 'العراق'}\n"
            f"📝 **التفاصيل:** {r[3] or 'لا توجد تفاصيل إضافية'}\n"
            f"📞 **التواصل:** {r[4] or 'غير متوفر'}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    await update.message.reply_text("اختر الخطوة التالية:", reply_markup=job_action_keyboard())


job_search_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(f'^({re.escape("🔍 بحث عن وظيفة")}|{re.escape(SEARCH_AGAIN_TEXT)})$'), latest_jobs_handler)],
    states={
        SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_job_search_query)],
    },
    fallbacks=[CommandHandler("cancel", cancel_job_search)],
)


ALERT_PAYMENT_ACCOUNT, ALERT_PAYMENT_SCREENSHOT = range(2)


async def alerts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)

    if not profile:
        await update.message.reply_text(
            "⚠️ أنشئ ملفك الشخصي أولاً من زر **👤 ملفي الشخصي** حتى نعرف أي وظائف نرسلها لك.",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
        return ConversationHandler.END

    conn = get_connection()
    active = conn.execute(
        "SELECT 1 FROM user_profiles WHERE user_id = ? AND is_subscribed_alerts = 1 "
        "AND (alerts_expires_at IS NULL OR alerts_expires_at > datetime('now'))", (user_id,)
    ).fetchone()
    conn.close()
    if active:
        await update.message.reply_text("✅ إشعارات الوظائف مفعلة لديك حالياً.", reply_markup=main_keyboard())
        return ConversationHandler.END
    await update.message.reply_text(
        "💰 اشتراك إشعارات الوظائف لمدة 30 يوماً: **1,000 د.ع**.\n\n"
        "أرسل اسم الحساب أو المحفظة التي دفعت منها:",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )
    return ALERT_PAYMENT_ACCOUNT


async def set_alert_payment_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['alert_payment_account'] = update.message.text.strip()
    await update.message.reply_text("أرسل الآن لقطة شاشة واضحة للتحويل كصورة مرفقة.", reply_markup=back_keyboard())
    return ALERT_PAYMENT_SCREENSHOT


async def set_alert_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("يرجى إرسال لقطة الشاشة كصورة مرفقة.", reply_markup=back_keyboard())
        return ALERT_PAYMENT_SCREENSHOT

    user_id = update.effective_user.id
    order_id = uuid.uuid4().hex
    file_id = update.message.photo[-1].file_id
    account = context.user_data['alert_payment_account']
    conn = get_connection()
    conn.execute(
        "INSERT INTO pending_alert_payments "
        "(order_id, user_id, payment_account, payment_screenshot_file_id) VALUES (?, ?, ?, ?)",
        (order_id, user_id, account, file_id),
    )
    conn.commit()
    conn.close()

    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول وتفعيل", callback_data=f"approve_alert:{order_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject_alert:{order_id}"),
    ]])
    caption = (
        "🔔 طلب تفعيل إشعارات الوظائف\n"
        f"🆔 المستخدم: {user_id}\n📦 الطلب: {order_id}\n"
        f"💰 المبلغ: 1,000 د.ع\n🏦 الحساب: {account}\n\nاختر الإجراء:"
    )
    try:
        await context.bot.send_photo(ADMIN_GROUP_ID, file_id, caption=caption, reply_markup=buttons)
    except Exception as error:
        logging.error("تعذر إرسال طلب اشتراك الإشعارات للأدمن: %s", error)
    await update.message.reply_text(
        "✅ تم رفع طلب الدفع. سيتم تفعيل الإشعارات بعد مراجعة الأدمن.",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


async def alert_payment_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("هذا الإجراء مخصص للأدمن فقط.", show_alert=True)
        return
    await query.answer()
    action, order_id = query.data.split(":", 1)
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id, status FROM pending_alert_payments WHERE order_id = ?", (order_id,)
    ).fetchone()
    if not row or row[1] != "pending":
        await query.edit_message_caption(caption="تم التعامل مع هذا الطلب مسبقاً.")
        conn.close()
        return
    user_id = row[0]
    if action == "approve_alert":
        conn.execute(
            "UPDATE user_profiles SET is_subscribed_alerts = 1, "
            "alerts_expires_at = datetime('now', '+30 days') WHERE user_id = ?", (user_id,)
        )
        conn.execute(
            "UPDATE pending_alert_payments SET status = 'approved', reviewed_at = CURRENT_TIMESTAMP "
            "WHERE order_id = ?", (order_id,)
        )
        conn.commit()
        await context.bot.send_message(user_id, "✅ تمت الموافقة وتفعيل إشعارات الوظائف لمدة 30 يوماً.")
        await query.edit_message_caption(caption=f"✅ تم تفعيل الاشتراك\nالطلب: {order_id}")
    else:
        conn.execute(
            "UPDATE pending_alert_payments SET status = 'rejected', reviewed_at = CURRENT_TIMESTAMP "
            "WHERE order_id = ?", (order_id,)
        )
        conn.commit()
        await context.bot.send_message(user_id, "❌ تم رفض طلب تفعيل الإشعارات. يرجى إرسال تحويل واضح.")
        await query.edit_message_caption(caption=f"❌ تم رفض الطلب\nالطلب: {order_id}")
    conn.close()


alert_payment_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(r'^🔔 تفعيل الإشعارات \(1,000 د\.ع\)$'), alerts_handler)],
    states={
        ALERT_PAYMENT_ACCOUNT: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_job_search), MessageHandler(filters.TEXT & ~filters.COMMAND, set_alert_payment_account)],
        ALERT_PAYMENT_SCREENSHOT: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_job_search), MessageHandler(filters.PHOTO, set_alert_payment_screenshot)],
    },
    fallbacks=[CommandHandler("cancel", cancel_job_search)],
)
