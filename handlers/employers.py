import logging
import re
import uuid
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
)

from config import ADMIN_GROUP_ID, ADMIN_ID, CHANNEL_USERNAME, DB_NAME
from database.connection import get_connection
from database.db import init_db
from ui import main_keyboard

# مراحل اختيار الخطة واستلام نص الإعلان الكامل
PLAN_CHOICE, JOB_TEXT, PAYMENT_ACCOUNT, PAYMENT_SCREENSHOT = range(4)
BACK_TEXT = "↩️ عودة"


def back_keyboard():
    return ReplyKeyboardMarkup([[BACK_TEXT]], resize_keyboard=True, one_time_keyboard=True)

# --- إنشاء جدول أصحاب الأعمال والاشتراكات ---
def init_employer_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employer_subscriptions (
            employer_id INTEGER PRIMARY KEY,
            plan_type TEXT,                -- 'single' (1000 د.ع) أو 'monthly' (5000 د.ع)
            jobs_left INTEGER DEFAULT 0,   -- الرصيد المتبقي من الوظائف
            expires_at DATETIME
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- جلب رصيد اشتراك صاحب العمل ---
def get_employer_quota(employer_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT plan_type, jobs_left, expires_at FROM employer_subscriptions "
        "WHERE employer_id = ? AND (expires_at IS NULL OR expires_at > datetime('now'))",
        (employer_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"plan_type": row[0], "jobs_left": row[1], "expires_at": row[2]}
    return None


def get_free_posts_used(user_id):
    conn = get_connection()
    row = conn.execute("SELECT free_job_posts_used FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else 0

# --- بدء الخطوات عند الضغط على "📢 نشر وظيفة (أصحاب الأعمال)" ---
async def start_employer_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    quota = get_employer_quota(user_id)

    plan_keyboard = [
        ["1️⃣ نشر وظيفة واحدة (1,000 د.ع)"],
        ["2️⃣ اشتراك شهري بلا حد (5,000 د.ع)"],
        [BACK_TEXT]
    ]

    # الاشتراك الشهري بلا حد خلال مدة صلاحيته.
    if quota and quota['plan_type'] == 'monthly':
        await update.message.reply_text(
            f"💼 **أهلاً بك يا صاحب العمل!**\n\n"
            f"رصيدك الحالي: **{quota['jobs_left']} وظيفة متبقية** في خطتك الشهرية.\n\n"
            "ألصق الآن نص إعلان الوظيفة كاملًا كما تريد نشره في القناة:",
            reply_markup=back_keyboard(),
            parse_mode="Markdown"
        )
        context.user_data['has_active_plan'] = True
        return JOB_TEXT

    free_posts_used = get_free_posts_used(user_id)
    if free_posts_used < 3:
        context.user_data['has_free_trial'] = True
        await update.message.reply_text(
            f"🎁 لديك تجربة نشر مجانية ({3 - free_posts_used} متبقية).\n\n"
            "ألصق نص إعلان الوظيفة كاملًا كما تريد نشره في القناة:",
            reply_markup=back_keyboard(),
        )
        return JOB_TEXT

    # انتهت التجارب المجانية، اطلب اختيار الدفع المحلي.
    context.user_data['has_free_trial'] = False
    context.user_data['has_active_plan'] = False
    await update.message.reply_text(
        "📢 **نشر إعلان وظيفة في شَدان**\n\n"
        "انتهت تجارب النشر المجانية. اختر طريقة الدفع المحلي، ثم أرسل اسم الحساب ولقطة التحويل.\n\n"
        "يتم التحقق عادة خلال 5 دقائق.",
        reply_markup=ReplyKeyboardMarkup(plan_keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return PLAN_CHOICE

# --- اختيار الخطة ---
async def set_plan_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "1,000" in text:
        context.user_data['selected_plan'] = "single"
        context.user_data['plan_price'] = 1000
    else:
        context.user_data['selected_plan'] = "monthly"
        context.user_data['plan_price'] = 5000

    await update.message.reply_text(
        "ألصق الآن نص إعلان الوظيفة كاملًا كما تريد نشره في القناة:",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )
    return JOB_TEXT

# --- استلام النص الكامل ونشر التجربة أو بدء الدفع المحلي ---
async def set_job_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    job_text = update.message.text.strip()
    if len(job_text) < 20:
        await update.message.reply_text("يرجى لصق نص إعلان كامل وواضح، وليس عنوانًا مختصرًا فقط.", reply_markup=back_keyboard())
        return JOB_TEXT

    order_id = uuid.uuid4().hex
    plan_type = (
        "monthly_active"
        if context.user_data.get('has_active_plan')
        else "free_trial"
        if context.user_data.get('has_free_trial')
        else context.user_data['selected_plan']
    )
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user_id,))
    conn.execute(
        "INSERT INTO pending_job_posts (order_id, user_id, job_text, plan_type) VALUES (?, ?, ?, ?)",
        (order_id, user_id, job_text, plan_type),
    )
    conn.commit()
    conn.close()

    if context.user_data.get('has_active_plan') or context.user_data.get('has_free_trial'):
        try:
            await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=job_text)
            conn = get_connection()
            conn.execute("UPDATE pending_job_posts SET status = 'published', published_at = CURRENT_TIMESTAMP WHERE order_id = ?", (order_id,))
            if context.user_data.get('has_free_trial'):
                conn.execute("UPDATE user_profiles SET free_job_posts_used = free_job_posts_used + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            if ADMIN_GROUP_ID and ADMIN_GROUP_ID != user_id:
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_GROUP_ID,
                        text=f"✅ تم نشر إعلان مباشر في القناة من المستخدم {user_id}.\n\n{job_text}",
                    )
                except Exception as error:
                    logging.error("تعذر إرسال إشعار النشر لمجموعة الأدمن %s: %s", ADMIN_GROUP_ID, error)
            await update.message.reply_text(
                "✅ تم نشر الإعلان مباشرة في القناة. سيقوم السكرابر بفهرسته لاحقًا تلقائيًا.",
                reply_markup=main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as error:
            logging.exception("فشل نشر إعلان المستخدم %s في القناة", user_id)
            await update.message.reply_text(
                f"تعذر النشر المباشر في القناة: {error}\nتأكد أن البوت مشرف في القناة وأن CHANNEL_USERNAME صحيح.",
                reply_markup=main_keyboard()
            )
    else:
        await update.message.reply_text(
            f"💰 المبلغ المطلوب: {1000 if context.user_data['selected_plan'] == 'single' else 5000:,} دينار عراقي.\n\n"
            "أرسل الآن اسم الحساب أو المحفظة التي دفعت منها:",
            reply_markup=back_keyboard(),
        )
        context.user_data['pending_order_id'] = order_id
        return PAYMENT_ACCOUNT

    return ConversationHandler.END


async def set_payment_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['payment_account'] = update.message.text.strip()
    await update.message.reply_text(
        "أرسل الآن لقطة شاشة واضحة للتحويل كصورة مرفقة.",
        reply_markup=back_keyboard(),
    )
    return PAYMENT_SCREENSHOT


async def set_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("يرجى إرسال لقطة الشاشة كصورة مرفقة.", reply_markup=back_keyboard())
        return PAYMENT_SCREENSHOT

    user_id = update.effective_user.id
    order_id = context.user_data['pending_order_id']
    file_id = update.message.photo[-1].file_id
    account = context.user_data['payment_account']
    conn = get_connection()
    conn.execute(
        "UPDATE pending_job_posts SET payment_account = ?, payment_screenshot_file_id = ?, "
        "payment_note = 'بانتظار موافقة الأدمن' WHERE order_id = ?",
        (account, file_id, order_id),
    )
    conn.commit()
    conn.close()

    admin_caption = (
        f"💳 طلب دفع محلي جديد\n"
        f"🆔 المستخدم: {user_id}\n"
        f"📦 الطلب: {order_id}\n"
        f"💰 الخطة: {'نشر منفرد - 1000' if context.user_data['selected_plan'] == 'single' else 'اشتراك شهري - 5000'} د.ع\n"
        f"🏦 الحساب الذي دفع منه: {account}\n\n"
        "التحقق عادة خلال 5 دقائق. اختر الإجراء:"
    )
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول ونشر", callback_data=f"approve_job:{order_id}"),
        InlineKeyboardButton("❌ رفض", callback_data=f"reject_job:{order_id}"),
    ]])
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=file_id,
            caption=admin_caption,
            reply_markup=buttons,
        )
    except Exception as error:
        logging.error("تعذر إرسال طلب الدفع إلى مجموعة الأدمن: %s", error)

    await update.message.reply_text(
        "✅ تم رفع طلب الدفع ولقطة الشاشة. يتم التحقق عادة خلال 5 دقائق، وسيتم نشر الإعلان بعد موافقة الأدمن.",
        reply_markup=main_keyboard(),
    )
    return ConversationHandler.END


async def payment_decision(update, context):
    query = update.callback_query
    if query.from_user.id != ADMIN_ID:
        await query.answer("هذا الإجراء مخصص للأدمن فقط.", show_alert=True)
        return
    await query.answer()
    action, order_id = query.data.split(":", 1)
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id, job_text, plan_type, status FROM pending_job_posts WHERE order_id = ?",
        (order_id,),
    ).fetchone()
    if not row or row[3] != 'pending':
        await query.edit_message_caption(caption="تم التعامل مع هذا الطلب مسبقًا.")
        conn.close()
        return

    user_id, job_text, plan_type, _ = row
    if action == "approve_job":
        try:
            await context.bot.send_message(chat_id=CHANNEL_USERNAME, text=job_text)
            if plan_type == "monthly":
                conn.execute(
                    "INSERT INTO employer_subscriptions (employer_id, plan_type, jobs_left, expires_at) "
                    "VALUES (?, 'monthly', 0, datetime('now', '+30 days')) "
                    "ON CONFLICT(employer_id) DO UPDATE SET plan_type = 'monthly', jobs_left = 0, expires_at = datetime('now', '+30 days')",
                    (user_id,),
                )
            conn.execute("UPDATE pending_job_posts SET status = 'published', published_at = CURRENT_TIMESTAMP WHERE order_id = ?", (order_id,))
            conn.commit()
            await context.bot.send_message(chat_id=user_id, text="✅ تمت الموافقة على الدفع ونُشر إعلانك في القناة.")
            await query.edit_message_caption(caption=f"✅ تمت الموافقة والنشر\nالطلب: {order_id}")
        except Exception as error:
            logging.error("فشل نشر الطلب المقبول: %s", error)
            await query.edit_message_caption(caption=f"تعذر النشر: {error}")
    else:
        conn.execute("UPDATE pending_job_posts SET status = 'rejected', payment_note = 'تم رفض الدفع' WHERE order_id = ?", (order_id,))
        conn.commit()
        await context.bot.send_message(chat_id=user_id, text="❌ لم تتم الموافقة على التحويل. يرجى إرسال تحويل واضح والتأكد من البيانات.")
        await query.edit_message_caption(caption=f"❌ تم رفض الطلب\nالطلب: {order_id}")
    conn.close()

# --- إلغاء العملية ---
async def cancel_employer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم الرجوع للقائمة الرئيسية.", reply_markup=main_keyboard())
    return ConversationHandler.END

# --- إنشاء الـ ConversationHandler الخاص بأصحاب الأعمال ---
employer_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex(r'^📢 نشر وظيفة \(أصحاب الأعمال\)$'), start_employer_post)
    ],
    states={
        PLAN_CHOICE: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_employer), MessageHandler(filters.TEXT & ~filters.COMMAND, set_plan_choice)],
        JOB_TEXT: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_employer), MessageHandler(filters.TEXT & ~filters.COMMAND, set_job_text)],
        PAYMENT_ACCOUNT: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_employer), MessageHandler(filters.TEXT & ~filters.COMMAND, set_payment_account)],
        PAYMENT_SCREENSHOT: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_employer), MessageHandler(filters.PHOTO, set_payment_screenshot)],
    },
    fallbacks=[CommandHandler('cancel', cancel_employer)]
)
