from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from config import ADMIN_ID, SUBSCRIPTION_CHANNEL_USERNAME


async def is_channel_subscriber(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(
            chat_id=SUBSCRIPTION_CHANNEL_USERNAME,
            user_id=user_id,
        )
    except TelegramError:
        return False

    return member.status in {"member", "administrator", "creator"} or (
        member.status == "restricted" and member.is_member
    )


async def subscription_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat or chat.type != "private" or user.id == ADMIN_ID:
        return

    if update.callback_query and update.callback_query.data == "check_subscription":
        return

    if await is_channel_subscriber(context, user.id):
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{SUBSCRIPTION_CHANNEL_USERNAME.lstrip('@')}")],
        [InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_subscription")],
    ])
    message = update.effective_message
    if message:
        await message.reply_text(
            "🔒 لاستخدام البوت، يجب الاشتراك أولاً في قناة شَدان.\n\n"
            "بعد الاشتراك اضغط على زر التحقق للمتابعة.",
            reply_markup=keyboard,
        )
    raise ApplicationHandlerStop


async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    if await is_channel_subscriber(context, query.from_user.id):
        await query.answer("تم التحقق من اشتراكك ✅")
        await query.edit_message_text("✅ تم التحقق من اشتراكك. أرسل /start لاستخدام البوت.")
        return

    await query.answer("لم يتم العثور على اشتراكك بعد.", show_alert=True)
