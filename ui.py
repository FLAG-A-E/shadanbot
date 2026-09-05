from telegram import KeyboardButton, ReplyKeyboardMarkup

BACK_TEXT = "↩️ عودة"


def main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🔍 بحث عن وظيفة"), KeyboardButton("🎯 وظائف تناسبني")],
        [KeyboardButton("👤 ملفي الشخصي"), KeyboardButton("🔔 تفعيل الإشعارات (1,000 د.ع)")],
        [KeyboardButton("📄 طلب CV احترافي (5,000)"), KeyboardButton("🎨 طلب بروتفوليو (10,000)")],
        [KeyboardButton("📢 نشر وظيفة (أصحاب الأعمال)")]
    ], resize_keyboard=True)


def back_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BACK_TEXT)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
