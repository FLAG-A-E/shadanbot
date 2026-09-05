import logging
import re
from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
)

from config import ADMIN_GROUP_ID, DB_NAME
from database.connection import get_connection
from database.db import init_db
from ui import main_keyboard

# مراحل جمع بيانات الـ CV / البرتفوليو
FULL_NAME, PHONE = range(2)
BACK_TEXT = "↩️ عودة"


def back_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton(BACK_TEXT)]], resize_keyboard=True, one_time_keyboard=True)

# --- إنشاء جدول الطلبات عند البداية ---
def init_services_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cv_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service_type TEXT,
            full_name TEXT,
            phone TEXT,
            experience TEXT,
            skills TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- بدء المحادثة ---
async def start_service_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "CV" in text:
        context.user_data['service_type'] = "CV احترافي (5,000 د.ع)"
        context.user_data['price'] = 5000
    else:
        context.user_data['service_type'] = "بروتفوليو/معرض أعمال (10,000 د.ع)"
        context.user_data['price'] = 10000

    await update.message.reply_text(
        f"🎯 **طلب {context.user_data['service_type']}**\n\n"
        "اكتب الاسم الذي تريد تسجيل الطلب به:\n\n"
        "**الخطوة 1 من 2:** الاسم:",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )
    return FULL_NAME

# --- الخطوة 1: الاسم ---
async def set_service_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['req_fullname'] = update.message.text.strip()
    await update.message.reply_text(
        "**الخطوة 2 من 2:** أرسل معرف تيليجرام أو رقم الهاتف للتواصل:\n"
        "*(مثال: @username أو 07700000000)*",
        reply_markup=back_keyboard(),
        parse_mode="Markdown"
    )
    return PHONE

# --- الخطوة 2: معرف تيليجرام أو رقم الهاتف ---
async def set_service_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['req_phone'] = update.message.text.strip()
    return await save_service_request(update, context)


# --- حفظ الطلب وإشعار مجموعة الأدمن ---
async def save_service_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # 1. حفظ الطلب في قاعدة البيانات
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO cv_requests (user_id, service_type, full_name, phone, experience, skills)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        user_id,
        context.user_data['service_type'],
        context.user_data['req_fullname'],
        context.user_data['req_phone'],
        "",
        ""
    ))
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # 2. إرسال إشعار فوري لك (كأدمن) بتفاصيل الطلب
    admin_msg = (
        f"📥 **طلب جديد رقم #{request_id}**\n\n"
        f"🛠️ **الخدمة:** {context.user_data['service_type']}\n"
        f"👤 **الاسم:** {context.user_data['req_fullname']}\n"
        f"📞 **التواصل:** {context.user_data['req_phone']}\n"
        f"🆔 **Telegram ID:** `{user_id}`\n"
        f"🔗 **Username:** @{update.effective_user.username or 'غير متوفر'}"
    )
    if ADMIN_GROUP_ID:
        try:
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=admin_msg, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"لم يتم إرسال الإشعار للأدمن: {e}")

    # 3. إجابة المستخدم وتوجيهه للدفع
    user_msg = (
        f"✅ **تم استلام معلومات طلبك بنجاح! (رقم الطلب: #{request_id})**\n\n"
        f"📌 **الخدمة:** {context.user_data['service_type']}\n"
        f"💰 **المبلغ المطلوب:** {context.user_data['price']:,} دينار عراقي\n\n"
        "تم رفع طلبك بنجاح. سيتواصل معك الأدمن لاحقاً."
    )

    await update.message.reply_text(user_msg, reply_markup=main_keyboard(), parse_mode="Markdown")
    return ConversationHandler.END

# --- إلغاء الطلب ---
async def cancel_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم الرجوع للقائمة الرئيسية.", reply_markup=main_keyboard())
    return ConversationHandler.END

# --- إنشاء الـ ConversationHandler الخاص بالخدمات ---
services_conv_handler = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex(r'^(📄 طلب CV احترافي \(5,000\)|🎨 طلب بروتفوليو \(10,000\))$'), start_service_request)
    ],
    states={
        FULL_NAME: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_service), MessageHandler(filters.TEXT & ~filters.COMMAND, set_service_fullname)],
        PHONE: [MessageHandler(filters.Regex(f'^{re.escape(BACK_TEXT)}$'), cancel_service), MessageHandler(filters.TEXT & ~filters.COMMAND, set_service_phone)],
    },
    fallbacks=[CommandHandler('cancel', cancel_service)]
)
