import os
import json
import logging
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ماژول‌های داخلی
from config import BOT_CONFIG
from database import (
    setup_database, check_user_exists, register_user, get_user_profile,
    register_referral, update_user_balance, get_all_users
)

# تنظیم لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# تابع برای جدا کردن اعداد سه رقم سه رقم
def format_number_with_commas(number):
    return "{:,}".format(int(number))

# تابع برای بررسی عضویت کاربر در کانال
async def check_channel_membership(update, context):
    user_id = update.effective_user.id
    
    # بررسی برای ادمین
    if user_id == BOT_CONFIG["admin-username"]:
        return True
    
    try:
        chat_member = await context.bot.get_chat_member(chat_id=BOT_CONFIG["ch-id"], user_id=user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"خطا در بررسی عضویت کاربر: {e}")
        return False

# تابع برای ارسال پیام عضویت در کانال
async def send_join_channel_message(update, context, referral_id=None):
    user_id = update.effective_user.id
    
    # ساخت دکمه‌های اینلاین
    keyboard = [
        [InlineKeyboardButton("کانال " + BOT_CONFIG["bot-name"], url=BOT_CONFIG["ch-username"])],
        [InlineKeyboardButton("عضو شدم!", callback_data=f"joinedch^{referral_id}" if referral_id else "joinedch^")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # تعیین متن پیام بر اساس نوع درخواست
    if referral_id:
        text = "سلام برای دریافت اعتبار هدیه و استفاده از ربات باید در کانال زیر عضو شوید \n\nپس از عضو شدن روی دکمه \"عضو شدم\" کلیک کنید!"
    else:
        text = "سلام برای ادامه فعالیت نیاز هست که داخل کانال زیر عضو شوید \n\nپس از عضو شدن روی دکمه \"عضو شدم\" کلیک کنید!"
    
    # ارسال پیام
    if update.callback_query:
        await update.callback_query.message.reply_text(text=text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=text, reply_markup=reply_markup)

# تابع برای ساخت منوی اصلی
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton(f"لیست خدمات {BOT_CONFIG['bot-name']}", callback_data="serviceslist^")],
        [
            InlineKeyboardButton("💎 اعتبار شما", callback_data="userprofile^"),
            InlineKeyboardButton("🛍 باشگاه مشتریان", callback_data="club^")
        ],
        [InlineKeyboardButton("❣️ دعوت از دوستان", callback_data="Invitefriends^")],
        [
            InlineKeyboardButton("» راهنما", callback_data="help^"),
            InlineKeyboardButton("» پشتیبانی", url=BOT_CONFIG["support-username"])
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# تابع برای پردازش دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username
    created_at = int(datetime.now().timestamp())
    
    # بررسی عضویت در کانال
    is_member = await check_channel_membership(update, context)
    if not is_member:
        # استخراج شناسه معرفی‌کننده اگر وجود داشته باشد
        referral_match = re.match(r'/start ref(\d+)', update.message.text) if update.message and update.message.text else None
        referral_id = referral_match.group(1) if referral_match else None
        
        await send_join_channel_message(update, context, referral_id)
        return
    
    # بررسی آیا کاربر با لینک معرفی آمده است
    if update.message and update.message.text and "ref" in update.message.text:
        referral_match = re.match(r'/start ref(\d+)', update.message.text)
        if referral_match:
            referral_id = referral_match.group(1)
            
            # بررسی خود-معرفی
            if str(user_id) == str(referral_id):
                await update.message.reply_text("شما نمی‌توانید با لینک خودتان وارد شوید! لطفاً دوستان خود را دعوت کنید.")
                return
            
            # بررسی وجود کاربر
            user_exists = check_user_exists(user_id)
            
            if not user_exists:
                # ثبت کاربر جدید
                register_user(user_id, username, created_at)
                
                # ثبت معرفی و به‌روزرسانی موجودی
                referal_amount = int(BOT_CONFIG["referal-creadit"])
                register_referral(int(referral_id), user_id, referal_amount)
                
                # ارسال پیام به کاربر جدید
                formatted_amount = format_number_with_commas(referal_amount)
                await update.message.reply_text(f"🎉 مبلغ {formatted_amount} تومان به کیف پول شما اضافه شد! 💰")
                
                # ارسال پیام به معرفی‌کننده
                try:
                    await context.bot.send_message(
                        chat_id=int(referral_id),
                        text=f"🎉 فردی با لینک شما وارد ربات شد و مبلغ {formatted_amount} تومان به کیف پول شما اضافه شد! 💰"
                    )
                except Exception as e:
                    logger.error(f"خطا در ارسال پیام به معرفی‌کننده: {e}")
                
                # ارسال پیام به ادمین
                try:
                    total_amount = referal_amount * 2
                    admin_message = (
                        f"📊 گزارش جدید | یک یوزر جدید با دعوت به ربات پیوست!\n\n"
                        f"- دعوت‌شونده: {user.first_name or 'نامشخص'} {user.last_name or 'نامشخص'} "
                        f"(@{user.username or 'نامشخص'})\n"
                        f"- مبلغ رفرال: {format_number_with_commas(total_amount)} تومان\n"
                        f"- دعوت‌کننده: {referral_id}\n"
                        f"- دعوت‌شونده: {user_id}"
                    )
                    await context.bot.send_message(
                        chat_id=BOT_CONFIG["admin-username"],
                        text=admin_message
                    )
                except Exception as e:
                    logger.error(f"خطا در ارسال پیام به ادمین: {e}")
            else:
                await update.message.reply_text("شما قبلاً در ربات عضو شده‌اید. 😉")
    
    # ثبت کاربر اگر وجود نداشته باشد
    if not check_user_exists(user_id):
        register_user(user_id, username, created_at)
        
        # ارسال اطلاعیه به ادمین
        try:
            # تبدیل تاریخ میلادی به شمسی (ساده‌سازی شده)
            persian_date = datetime.now().strftime("%Y/%m/%d").replace(
                str(datetime.now().year), str(datetime.now().year - 622)
            )
            
            admin_message = (
                f"📢 #کاربر_جدید ربات شما را استارت کرد!\n\n"
                f"🔹 **نام کاربر**: {user.first_name}\n"
                f"🔹 **شناسه کاربر**: [{user_id}](https://t.me/{username or ''})\n"
                f"🔹 **زمان استارت**: `{persian_date}`"
            )
            await context.bot.send_message(
                chat_id=BOT_CONFIG["admin-username"],
                text=admin_message,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"خطا در ارسال پیام به ادمین: {e}")
    
    # ارسال منوی اصلی
    await update.message.reply_text(
        f"کاربر گرامی\nلطفا یکی از گزینه‌های زیر رو برای {BOT_CONFIG['bot-name']} انتخاب کنید :",
        reply_markup=get_main_menu_keyboard()
    )

# تابع برای پردازش کلیک روی دکمه‌های اینلاین
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    user_id = query.from_user.id
    
    # بررسی عضویت در کانال
    is_member = await check_channel_membership(update, context)
    if not is_member and not callback_data.startswith("joinedch^"):
        await send_join_channel_message(update, context)
        return
    
    # پردازش دکمه "عضو شدم"
    if callback_data.startswith("joinedch^"):
        referral_match = re.match(r'joinedch\^(\d+)', callback_data)
        if referral_match:
            referral_id = referral_match.group(1)
            
            # بررسی مجدد عضویت در کانال
            is_member = await check_channel_membership(update, context)
            if not is_member:
                await query.edit_message_text(
                    "هنوز عضو نشدید! اول عضو شوید و سپس روی \"عضو شدم\" کلیک کنید!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"کانال {BOT_CONFIG['bot-name']}", url=BOT_CONFIG["ch-username"])],
                        [InlineKeyboardButton("عضو شدم!", callback_data=callback_data)]
                    ])
                )
                return
            
            # بررسی خود-معرفی
            if str(user_id) == str(referral_id):
                await query.edit_message_text(
                    "شما نمی‌توانید با لینک خودتان وارد شوید! لطفاً دوستان خود را دعوت کنید.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("دعوت از دوستان", callback_data="Invitefriends^")]
                    ])
                )
                return
            
            # بررسی وجود کاربر
            user_exists = check_user_exists(user_id)
            created_at = int(datetime.now().timestamp())
            
            if not user_exists:
                # ثبت کاربر جدید
                register_user(user_id, query.from_user.username, created_at)
                
                # ثبت معرفی و به‌روزرسانی موجودی
                referal_amount = int(BOT_CONFIG["referal-creadit"])
                register_referral(int(referral_id), user_id, referal_amount)
                
                # ارسال پیام به کاربر جدید
                formatted_amount = format_number_with_commas(referal_amount)
                await query.edit_message_text(
                    f"🎉 مبلغ {formatted_amount} تومان به کیف پول شما اضافه شد! 💰",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("دریافت منو", callback_data="userpanel^")]
                    ])
                )
                
                # ارسال پیام به معرفی‌کننده
                try:
                    await context.bot.send_message(
                        chat_id=int(referral_id),
                        text=f"🎉 فردی با لینک شما وارد ربات شد و مبلغ {formatted_amount} تومان به کیف پول شما اضافه شد! 💰"
                    )
                except Exception as e:
                    logger.error(f"خطا در ارسال پیام به معرفی‌کننده: {e}")
                
                # ارسال پیام به ادمین
                try:
                    total_amount = referal_amount * 2
                    admin_message = (
                        f"📊 گزارش جدید | یک یوزر جدید با دعوت به ربات پیوست!\n\n"
                        f"- دعوت‌شونده: {query.from_user.first_name or 'نامشخص'} {query.from_user.last_name or 'نامشخص'} "
                        f"(@{query.from_user.username or 'نامشخص'})\n"
                        f"- مبلغ رفرال: {format_number_with_commas(total_amount)} تومان\n"
                        f"- دعوت‌کننده: {referral_id}\n"
                        f"- دعوت‌شونده: {user_id}"
                    )
                    await context.bot.send_message(
                        chat_id=BOT_CONFIG["admin-username"],
                        text=admin_message
                    )
                except Exception as e:
                    logger.error(f"خطا در ارسال پیام به ادمین: {e}")
            else:
                await query.edit_message_text(
                    "📌 شما با موفقیت به کانال " + BOT_CONFIG["bot-name"] + " پیوستید.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("» دریافت منو", callback_data="userpanel^")]
                    ])
                )
        else:
            # اگر بدون معرفی عضو شده باشد
            await query.edit_message_text(
                "📌 شما با موفقیت به کانال " + BOT_CONFIG["bot-name"] + " پیوستید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("» دریافت منو", callback_data="userpanel^")]
                ])
            )
        return
    
    # پردازش سایر دکمه‌ها
    if callback_data == "userpanel^":
        await query.edit_message_text(
            f"کاربر گرامی\nلطفا یکی از گزینه‌های زیر رو برای {BOT_CONFIG['bot-name']} انتخاب کنید :",
            reply_markup=get_main_menu_keyboard()
        )
    
    elif callback_data == "help^":
        await query.edit_message_text(
            f"📌 راهنمای استفاده از {BOT_CONFIG['bot-name']}\n\n[... به زودی ...]",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("» بازگشت", callback_data="userpanel^")]
            ])
        )
    
    elif callback_data == "serviceslist^":
        user_id = query.from_user.id
        await query.edit_message_text(
            f"📌 لطفاً یکی از خدمات {BOT_CONFIG['bot-name']} را انتخاب کنید :",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("درخواست پرینت یا کپی", url=f"https://pelicanstudio.ir/coffenetmehdi?user_id={user_id}")],
                [InlineKeyboardButton("» بازگشت", callback_data="userpanel^")]
            ])
        )
    
    elif callback_data == "club^":
        await query.edit_message_text(
            "📌 باشگاه مشتریان\n\nبه باشگاه مشتریان خوش آمدید! اینجا می‌توانید از تخفیف‌ها و پیشنهادات ویژه ما بهره‌مند شوید.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔥 کدهای تخفیف", callback_data="disscount_offers^"),
                    InlineKeyboardButton("🏄 پیشنهادات ویژه شما", callback_data="special_offers^")
                ],
                [InlineKeyboardButton("» بازگشت", callback_data="userpanel^")]
            ])
        )
    
    elif callback_data == "userprofile^":
        # دریافت اطلاعات پروفایل کاربر
        profile = get_user_profile(user_id)
        
        # فرمت‌بندی مقادیر
        formatted_balance = format_number_with_commas(profile["balance"])
        formatted_total_inviter_cart = format_number_with_commas(profile["totalInviterCart"])
        
        # ساخت متن پیام
        username_text = f"@{query.from_user.username}" if query.from_user.username else ""
        message_text = (
            f"اطلاعات حساب شما:\n\n"
            f"نام کاربری: {username_text}\n"
            f"موجودی: {formatted_balance} تومان\n\n"
            f"تعداد دعوت‌ها: {profile['referralCount']}\n"
            f"مبلغ هدیه دریافتی: {formatted_total_inviter_cart}"
        )
        
        # ارسال پیام
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("» اعتبار هدیه", callback_data="Invitefriends^"),
                    InlineKeyboardButton("» افزایش موجودی", callback_data="increasebalance^")
                ],
                [InlineKeyboardButton("» بازگشت", callback_data="userpanel^")]
            ])
        )
    
    elif callback_data == "Invitefriends^":
        # ساخت پیام دعوت
        user_id = query.from_user.id
        bot_username = BOT_CONFIG["bot-username"]
        referal_creadit = BOT_CONFIG["referal-creadit"]
        bot_name = BOT_CONFIG["bot-name"]
        
        invite_message = (
            f"شما به ربات {bot_name} دعوت شدید! 🤝\n\n"
            f"این ربات به شما کمک میکنه بدون مراجعه به کافی‌نت کارهاتون رو غیرحضوری انجام بدید. "
            f"با این لینک دعوت {referal_creadit} تومان اعتبار هدیه دریافت کنید!"
        )
        
        encoded_invite_message = invite_message.replace(" ", "%20").replace("\n", "%0A")
        invite_link = f"http://t.me/share/url?url=https://t.me/{bot_username}?start=ref{user_id}&text={encoded_invite_message}"
        
        await query.edit_message_text(
            f"به ازاء دعوت هر نفر به {bot_name} توسط شما، {referal_creadit} تومان اعتبار هدیه برای شما ثبت می‌شود.\n\n"
            "روی دکمه «ارسال پیام دعوت» کلیک کنید و پیام دعوت رو با دوستانتان به اشتراک بگذارید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 ارسال پیام دعوت 📩", url=invite_link)],
                [InlineKeyboardButton("» بازگشت", callback_data="userpanel^")]
            ])
        )
    
    # دستور ادمین برای نمایش آمار
    elif callback_data == "admin_stats^" and user_id == BOT_CONFIG["admin-username"]:
        # دریافت آمار کاربران
        try:
            from database import get_all_users
            users = get_all_users()
            user_count = len(users)
            
            # ارسال آمار به ادمین
            stats_message = f"📊 آمار ربات {BOT_CONFIG['bot-name']}\n\n"
            stats_message += f"👥 تعداد کل کاربران: {user_count}\n"
            
            # ارسال پیام
            await query.edit_message_text(
                stats_message,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("» بازگشت به پنل ادمین", callback_data="admin_panel^")]
                ])
            )
        except Exception as e:
            logger.error(f"خطا در نمایش آمار: {e}")
            await query.edit_message_text(
                "خطا در دریافت آمار!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("» بازگشت", callback_data="userpanel^")]
                ])
            )

# تابع برای پردازش دستور /admin
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # بررسی دسترسی ادمین
    if user_id != BOT_CONFIG["admin-username"]:
        await update.message.reply_text("شما دسترسی به این بخش را ندارید!")
        return
    
    # ساخت منوی ادمین
    keyboard = [
        [InlineKeyboardButton("📊 آمار کاربران", callback_data="admin_stats^")],
        [InlineKeyboardButton("💰 مدیریت اعتبارات", callback_data="admin_credits^")],
        [InlineKeyboardButton("» بازگشت به منوی اصلی", callback_data="userpanel^")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👨‍💻 پنل مدیریت {BOT_CONFIG['bot-name']}\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=reply_markup
    )

# تابع برای پردازش پیام‌های متنی
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith('/start'):
        await start(update, context)
    elif update.message.text.startswith('/admin'):
        await admin_command(update, context)
    else:
        # پاسخ به پیام‌های نامشخص
        await update.message.reply_text("متوجه نشدم چی گفتی! لطفاً دوباره تلاش کنید. 🤔")

# تابع اصلی
def main():
    # ایجاد پایگاه داده
    setup_database()
    
    # ایجاد اپلیکیشن
    application = Application.builder().token(BOT_CONFIG["TOKEN"]).build()
    
    # اضافه کردن هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # شروع پولینگ
    logger.info(f"ربات {BOT_CONFIG['bot-name']} شروع به کار کرد...")
    application.run_polling()

if __name__ == "__main__":
    main() 