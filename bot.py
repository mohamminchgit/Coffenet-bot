import os
import json
import logging
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import matplotlib.pyplot as plt
import io
import matplotlib
import jdatetime
from matplotlib import font_manager
import arabic_reshaper
from bidi.algorithm import get_display

# ماژول‌های داخلی
from config import BOT_CONFIG
from database import (
    setup_database, check_user_exists, register_user, get_user_profile,
    register_referral, update_user_balance, get_all_users, register_transaction,
    update_transaction_status, get_transaction_by_message_id, get_user_transactions,
    get_card_info, set_card_info, get_stats, get_top_inviters, get_loyal_users,
    get_growth_chart, get_usernames, get_referrals_by_inviter,
    get_top_inviter_by_amount, get_top_inviter_by_count, get_total_referral_rewards
)

# تنظیم لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# مراحل گفتگو برای افزایش موجودی
PAYMENT_METHOD, ENTER_AMOUNT, CONFIRM_AMOUNT, SEND_RECEIPT = range(4)

# ذخیره اطلاعات موقت کاربر
user_payment_data = {}

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
    
    # بررسی پارامترهای خاص در دستور start
    if update.message and update.message.text and update.message.text.startswith('/start'):
        message_text = update.message.text
        
        if "reject_" in message_text:
            # پردازش رد پرداخت توسط ادمین
            parts = message_text.split("reject_")[1].split("_")
            if len(parts) >= 2:
                payment_user_id = int(parts[0])
                message_id = int(parts[1])
                
                # تنظیم وضعیت برای دریافت دلیل رد
                context.user_data["reject_payment"] = {
                    "user_id": payment_user_id,
                    "message_id": message_id
                }
                
                # ارسال پیام و ذخیره شناسه آن برای ویرایش بعدی
                msg = await update.message.reply_text(
                    "لطفاً دلیل رد پرداخت را وارد کنید:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ لغو", callback_data="userpanel^")]
                    ])
                )
                context.user_data["reject_payment"]["prompt_message_id"] = msg.message_id
                return
                
        elif "custom_" in message_text:
            # پردازش تأیید با مبلغ دلخواه
            parts = message_text.split("custom_")[1].split("_")
            if len(parts) >= 2:
                payment_user_id = int(parts[0])
                message_id = int(parts[1])
                
                # تنظیم وضعیت برای دریافت مبلغ دلخواه
                context.user_data["custom_amount"] = {
                    "user_id": payment_user_id,
                    "message_id": message_id
                }
                
                # ارسال پیام و ذخیره شناسه آن برای ویرایش بعدی
                msg = await update.message.reply_text(
                    "لطفاً مبلغ دلخواه را به تومان وارد کنید:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ لغو", callback_data="userpanel^")]
                    ])
                )
                context.user_data["custom_amount"]["prompt_message_id"] = msg.message_id
                return
    
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
    
    elif callback_data == "increasebalance^":
        # منوی افزایش موجودی
        await query.edit_message_text(
            "💰 افزایش اعتبار\n\n"
            "برای افزایش اعتبار حساب خود، می‌توانید از روش پرداخت کارت به کارت استفاده کنید.\n\n"
            "لطفاً روش پرداخت خود را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 کارت به کارت", callback_data="payment_method^card")],
                [InlineKeyboardButton("🔄 درگاه آنلاین (غیرفعال)", callback_data="payment_method^online")],
                [InlineKeyboardButton("❌ لغو", callback_data="userprofile^")]
            ])
        )
    
    elif callback_data == "payment_method^online":
        # اطلاع‌رسانی درباره غیرفعال بودن درگاه آنلاین
        await query.answer("فعلا موقتا غیر فعال است. لطفاً از روش کارت به کارت استفاده کنید.", show_alert=True)
    
    elif callback_data == "payment_method^card":
        # شروع فرآیند پرداخت کارت به کارت
        user_payment_data[user_id] = {"state": ENTER_AMOUNT}
        
        await query.edit_message_text(
            "💰 افزایش اعتبار با کارت به کارت\n\n"
            "لطفاً مبلغ مورد نظر خود را به تومان وارد کنید:\n"
            "(مثال: 50,000)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ لغو", callback_data="increasebalance^")]
            ])
        )
        
        # تنظیم وضعیت گفتگو
        context.user_data["payment_state"] = ENTER_AMOUNT
    
    elif callback_data.startswith("confirm_payment^"):
        # تأیید مبلغ پرداخت
        amount = callback_data.split("^")[1]
        user_payment_data[user_id]["amount"] = amount
        formatted_amount = format_number_with_commas(amount)
        
        await query.edit_message_text(
            f"✅ تأیید پرداخت\n\n"
            f"مبلغ {formatted_amount} تومان برای شارژ انتخاب شد.\n\n"
            f"لطفاً به شماره کارت زیر واریز کرده و سپس اسکرین‌شات رسید پرداخت خود را ارسال کنید:\n\n"
            f"شماره کارت: {BOT_CONFIG['card_number']}\n"
            f"به نام: {BOT_CONFIG['card_holder']}\n\n"
            f"🔹 توجه: بعد از واریز، لطفاً فقط تصویر رسید پرداخت را به صورت عکس واضح ارسال کنید",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ لغو", callback_data="increasebalance^")]
            ])
        )
        
        # تنظیم وضعیت گفتگو
        context.user_data["payment_state"] = CONFIRM_AMOUNT
    
    elif callback_data.startswith("cancel_payment^"):
        # لغو فرآیند پرداخت
        if user_id in user_payment_data:
            del user_payment_data[user_id]
        
        await query.edit_message_text(
            "❌ درخواست افزایش اعتبار لغو شد.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("» بازگشت به پروفایل", callback_data="userprofile^")]
            ])
        )
    
    elif callback_data.startswith("admin_approve_payment^"):
        # تأیید پرداخت توسط ادمین
        parts = callback_data.split("^")
        payment_user_id = int(parts[1])
        amount = int(parts[2])
        message_id = int(parts[3])
        
        # افزایش موجودی کاربر
        update_user_balance(payment_user_id, amount)
        
        # به‌روزرسانی وضعیت تراکنش
        update_transaction_status(message_id, "approved")
        
        # ارسال پیام به کاربر
        try:
            await context.bot.send_message(
                chat_id=payment_user_id,
                text=f"✅ پرداخت شما تأیید شد!\n\n"
                     f"مبلغ {format_number_with_commas(amount)} تومان به اعتبار شما افزوده شد."
            )
        except Exception as e:
            logger.error(f"خطا در ارسال پیام به کاربر: {e}")
        
        # به‌روزرسانی پیام در کانال ادمین
        await context.bot.edit_message_caption(
            chat_id=BOT_CONFIG["order-channel-id"],
            message_id=message_id,
            caption=f"✅ پرداخت تأیید شد\n\n"
                 f"کاربر: {payment_user_id}\n"
                 f"مبلغ: {format_number_with_commas(amount)} تومان\n"
                 f"وضعیت: تأیید شده توسط ادمین",
            reply_markup=None
        )
        
        # پاسخ به ادمین
        await query.answer("پرداخت با موفقیت تأیید شد و اعتبار کاربر افزایش یافت.", show_alert=True)
    
    elif callback_data.startswith("admin_reject_payment^"):
        # رد پرداخت توسط ادمین
        parts = callback_data.split("^")
        payment_user_id = int(parts[1])
        message_id = int(parts[3])
        
        # به‌روزرسانی وضعیت تراکنش
        update_transaction_status(message_id, "rejected")
        
        # ایجاد لینک برای ادمین جهت ارسال دلیل رد پرداخت
        reject_link = f"https://t.me/{BOT_CONFIG['bot-username']}?start=reject_{payment_user_id}_{message_id}"
        
        # ارسال پیام به ادمین
        await query.edit_message_text(
            "لطفاً روی لینک زیر کلیک کنید و دلیل رد پرداخت را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 ارسال دلیل رد پرداخت", url=reject_link)]
            ])
        )
    
    elif callback_data.startswith("admin_custom_amount^"):
        # تأیید با مبلغ دلخواه
        parts = callback_data.split("^")
        payment_user_id = int(parts[1])
        message_id = int(parts[3])
        
        # ایجاد لینک برای ادمین جهت وارد کردن مبلغ دلخواه
        custom_amount_link = f"https://t.me/{BOT_CONFIG['bot-username']}?start=custom_{payment_user_id}_{message_id}"
        
        # ارسال پیام به ادمین
        await query.edit_message_text(
            "لطفاً روی لینک زیر کلیک کنید و مبلغ دلخواه را وارد کنید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 وارد کردن مبلغ دلخواه", url=custom_amount_link)]
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
        # منوی دسته‌بندی آمار
        stats_menu = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 آمار زمانی و روند رشد", callback_data="admin_stats_time^")],
            [InlineKeyboardButton("🤝 آمار دعوت و رفرال", callback_data="admin_stats_referral^")],
            [InlineKeyboardButton("💰 آمار مالی و تراکنش", callback_data="admin_stats_finance^")],
            [InlineKeyboardButton("👤 آمار رفتار کاربران", callback_data="admin_stats_behavior^")],
            [InlineKeyboardButton("» بازگشت به پنل ادمین", callback_data="admin_panel^")]
        ])
        await query.edit_message_text(
            "لطفاً یکی از دسته‌های آمار زیر را انتخاب کنید:",
            reply_markup=stats_menu
        )
        return

    elif callback_data == "admin_stats_referral^" and user_id == BOT_CONFIG["admin-username"]:
        stats = get_stats()
        top_inviters = get_top_inviters()
        user_ids = [uid for uid, _ in top_inviters]
        usernames = get_usernames(user_ids)
        # آمارهای ویژه
        top_amount = get_top_inviter_by_amount()
        top_count = get_top_inviter_by_count()
        total_inviter, total_invitee = get_total_referral_rewards()
        msg = "🤝 آمار دعوت و رفرال\n\n"
        if top_amount:
            msg += f"🏆 بیشترین درآمد از دعوت: @{top_amount[1] or 'بدون_نام'} ({top_amount[0]}) با {format_number_with_commas(top_amount[2])} تومان\n"
        if top_count:
            msg += f"👑 بیشترین دعوت موفق: @{top_count[1] or 'بدون_نام'} ({top_count[0]}) با {top_count[2]} دعوت\n"
        msg += f"💸 مجموع کل پاداش پرداختی:\n  - دعوت‌کنندگان: {format_number_with_commas(total_inviter)} تومان\n  - دعوت‌شونده‌ها: {format_number_with_commas(total_invitee)} تومان\n\n"
        msg += "برترین دعوت‌کنندگان:\n"
        buttons = []
        for idx, (uid, count) in enumerate(top_inviters, 1):
            uname = usernames.get(uid, "بدون نام کاربری")
            msg += f"{idx}. {uname} ({uid}) - {count} دعوت موفق\n"
            buttons.append([InlineKeyboardButton(f"جزئیات دعوت‌های {uname}", callback_data=f"referral_details^{uid}")])
        buttons.append([InlineKeyboardButton("» بازگشت به آمار", callback_data="admin_stats^")])
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    elif callback_data.startswith("referral_details^") and user_id == BOT_CONFIG["admin-username"]:
        inviter_id = int(callback_data.split("^")[1])
        referrals = get_referrals_by_inviter(inviter_id)
        if not referrals:
            await query.edit_message_text("این کاربر هیچ دعوت موفقی نداشته است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("» بازگشت", callback_data="admin_stats_referral^")]]))
            return
        msg = f"📋 لیست کاربران دعوت‌شده توسط {inviter_id}:\n\n"
        for idx, ref in enumerate(referrals, 1):
            uname = ref['username'] or 'بدون نام کاربری'
            created = datetime.fromtimestamp(ref['created_at']).strftime('%Y/%m/%d') if ref['created_at'] else '-'
            ref_date = ref['referral_date'][:10] if ref['referral_date'] else '-'
            msg += f"{idx}. {uname} ({ref['invitee_user_id']}) | ثبت‌نام: {created} | دعوت: {ref_date}\n"
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("» بازگشت", callback_data="admin_stats_referral^")]])
        )
        return

    elif callback_data == "admin_stats_time^" and user_id == BOT_CONFIG["admin-username"]:
        stats = get_stats()
        msg = "📈 آمار زمانی و روند رشد\n\n"
        msg += f"کاربران امروز: {stats['today_users']}\n"
        msg += f"کاربران دیروز: {stats['yesterday_users']}\n"
        msg += f"کاربران هفته گذشته: {stats['week_users']}\n"
        msg += f"کاربران فعال امروز: {stats['active_today']}\n\n"
        msg += "برای دریافت نمودار گرافیکی، یکی از بازه‌های زیر را انتخاب کنید:\n"
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("نمودار ۱۴ روز اخیر", callback_data="growth_chart^14")],
                [InlineKeyboardButton("نمودار ۱ ماه اخیر", callback_data="growth_chart^30")],
                [InlineKeyboardButton("نمودار ۳ ماه اخیر", callback_data="growth_chart^90")],
                [InlineKeyboardButton("» بازگشت به آمار", callback_data="admin_stats^")]
            ])
        )
        return

    elif callback_data == "admin_stats_finance^" and user_id == BOT_CONFIG["admin-username"]:
        stats = get_stats()
        msg = "💰 آمار مالی و تراکنش\n\n"
        msg += f"مجموع موجودی کاربران: {format_number_with_commas(stats['total_balance'])} تومان\n"
        # می‌توان آمارهای جزئی‌تر را اینجا اضافه کرد (مثلاً مجموع تراکنش‌های موفق)
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("» بازگشت به آمار", callback_data="admin_stats^")]
            ])
        )
        return

    elif callback_data == "admin_stats_behavior^" and user_id == BOT_CONFIG["admin-username"]:
        stats = get_stats()
        loyal_users = get_loyal_users()
        user_ids = [uid for uid, _ in loyal_users]
        usernames = get_usernames(user_ids)
        msg = "👤 آمار رفتار کاربران\n\n"
        msg += f"تعداد کل کاربران: {stats['total_users']}\n\n"
        msg += "کاربران وفادار (فعال در حداقل ۲ هفته):\n"
        for idx, (uid, weeks) in enumerate(loyal_users, 1):
            uname = usernames.get(uid) or "بدون نام کاربری"
            msg += f"{idx}. {uname} ({uid}) - {weeks} هفته فعال\n"
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("» بازگشت به آمار", callback_data="admin_stats^")]
            ])
        )
        return

    # پنل ادمین
    elif callback_data == "admin_panel^":
        if user_id != BOT_CONFIG["admin-username"]:
            await query.edit_message_text(
                "شما دسترسی به این بخش را ندارید!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("» بازگشت به منوی اصلی", callback_data="userpanel^")]
                ])
            )
            return
            
        # ساخت منوی ادمین
        keyboard = [
            [InlineKeyboardButton("📊 آمار کاربران", callback_data="admin_stats^")],
            [InlineKeyboardButton("💰 مدیریت اعتبارات", callback_data="admin_credits^")],
            [InlineKeyboardButton("💳 تغییر شماره کارت/نام کارت", callback_data="admin_cardinfo^")],
            [InlineKeyboardButton("» بازگشت به منوی اصلی", callback_data="userpanel^")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"👨‍💻 پنل مدیریت {BOT_CONFIG['bot-name']}\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=reply_markup
        )

    elif callback_data == "admin_cardinfo^":
        if user_id != BOT_CONFIG["admin-username"]:
            await query.edit_message_text(
                "شما دسترسی به این بخش را ندارید!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("» بازگشت به منوی اصلی", callback_data="userpanel^")]
                ])
            )
            return
        context.user_data["awaiting_card_info"] = True
        await query.edit_message_text(
            f"شماره کارت فعلی: {BOT_CONFIG['card_number']}\n"
            f"به نام: {BOT_CONFIG['card_holder']}\n\n"
            "لطفاً شماره کارت جدید و نام صاحب کارت را به صورت زیر وارد کنید:\n"
            "6037991521965867, محمد امین چهاردولی",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("» بازگشت به پنل ادمین", callback_data="admin_panel^")]
            ])
        )

    elif callback_data.startswith("growth_chart^") and user_id == BOT_CONFIG["admin-username"]:
        matplotlib.rcParams['font.sans-serif'] = ['Tahoma', 'Vazirmatn', 'IRANSans', 'Arial']
        days = int(callback_data.split("^")[1])
        growth = get_growth_chart(days)
        if not growth:
            await query.edit_message_text("داده‌ای برای رسم نمودار وجود ندارد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("» بازگشت", callback_data="admin_stats_time^")]]))
            return
        dates = [jdatetime.date.fromgregorian(date=datetime.strptime(d, "%Y-%m-%d").date()).strftime("%Y/%m/%d") for d, _ in growth]
        counts = [c for _, c in growth]
        font_path = "AbarMid-Bold.ttf"
        prop = font_manager.FontProperties(fname=font_path)
        def fa(text):
            return get_display(arabic_reshaper.reshape(text))
        if days >= 60:
            # گروه‌بندی بر اساس ماه
            import collections
            month_map = collections.OrderedDict()
            for d, c in growth:
                date_obj = jdatetime.date.fromgregorian(date=datetime.strptime(d, "%Y-%m-%d").date())
                key = f"{date_obj.year}/{date_obj.month:02d}"
                month_map.setdefault(key, 0)
                month_map[key] += c

            # برچسب محور x را با نام ماه شمسی بساز
            x_labels = [fa(k) for k in month_map.keys()]
            y_vals = list(month_map.values())

            fig, ax = plt.subplots(figsize=(9,5))
            ax.plot(x_labels, y_vals, marker='o', color='#1976D2', linewidth=3, markersize=8, markerfacecolor='#FF9800', markeredgewidth=2)
            ax.fill_between(x_labels, y_vals, color='#1976D2', alpha=0.08)
            ax.set_title(fa(f'نمودار رشد کاربران {days} روز اخیر'), fontproperties=prop, fontsize=18, color='#222')
            ax.set_xlabel(fa('ماه'), fontproperties=prop, fontsize=14, color='#444')
            ax.set_ylabel(fa('تعداد ثبت‌نام'), fontproperties=prop, fontsize=14, color='#444')
            ax.tick_params(axis='x', labelsize=13)
            ax.tick_params(axis='y', labelsize=12)
            for label in ax.get_xticklabels():
                label.set_fontproperties(prop)
            for label in ax.get_yticklabels():
                label.set_fontproperties(prop)
            ax.grid(True, linestyle='--', alpha=0.4)
            fig.patch.set_facecolor('#f7f7fa')
            plt.tight_layout()
        else:
            # حالت روزانه مثل قبل
            plt.style.use('seaborn-v0_8-darkgrid')
            fig, ax = plt.subplots(figsize=(9,5))
            ax.plot(dates, counts, marker='o', color='#1976D2', linewidth=3, markersize=8, markerfacecolor='#FF9800', markeredgewidth=2)
            ax.fill_between(dates, counts, color='#1976D2', alpha=0.08)
            ax.set_title(fa(f'نمودار رشد کاربران {days} روز اخیر'), fontproperties=prop, fontsize=18, color='#222')
            ax.set_xlabel(fa('تاریخ'), fontproperties=prop, fontsize=14, color='#444')
            ax.set_ylabel(fa('تعداد ثبت‌نام'), fontproperties=prop, fontsize=14, color='#444')
            ax.tick_params(axis='x', labelrotation=45, labelsize=12)
            ax.tick_params(axis='y', labelsize=12)
            for label in ax.get_xticklabels():
                label.set_fontproperties(prop)
            for label in ax.get_yticklabels():
                label.set_fontproperties(prop)
            ax.grid(True, linestyle='--', alpha=0.4)
            fig.patch.set_facecolor('#f7f7fa')
            plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        await query.message.reply_photo(photo=buf, caption=f'نمودار رشد کاربران {days} روز اخیر')
        buf.close()
        plt.close()
        await query.edit_message_text(
            f"نمودار رشد کاربران {days} روز اخیر ارسال شد.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("» بازگشت به آمار زمانی", callback_data="admin_stats_time^")]
            ])
        )
        return

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
        [InlineKeyboardButton("💳 تغییر شماره کارت/نام کارت", callback_data="admin_cardinfo^")],
        [InlineKeyboardButton("» بازگشت به منوی اصلی", callback_data="userpanel^")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👨‍💻 پنل مدیریت {BOT_CONFIG['bot-name']}\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=reply_markup
    )

# تابع برای پردازش پیام‌های متنی
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # لاگ برای دیباگ
    logger.info(f"دریافت پیام از کاربر {user_id}")
    
    # بررسی وضعیت گفتگو
    if "payment_state" in context.user_data:
        payment_state = context.user_data["payment_state"]
        logger.info(f"وضعیت پرداخت کاربر {user_id}: {payment_state}")
        
        if payment_state == ENTER_AMOUNT:
            # پردازش مبلغ وارد شده
            message_text = update.message.text
            try:
                # حذف کاراکترهای اضافی و تبدیل به عدد
                amount_text = message_text.replace(",", "").replace("،", "").strip()
                amount = int(amount_text)
                
                if amount < 10000:
                    await update.message.reply_text(
                        "❌ مبلغ وارد شده باید حداقل 10,000 تومان باشد.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 تلاش مجدد", callback_data="payment_method^card")],
                            [InlineKeyboardButton("❌ لغو", callback_data="increasebalance^")]
                        ])
                    )
                    return
                
                # ذخیره مبلغ
                user_payment_data[user_id] = {"amount": amount}
                
                # ویرایش پیام قبلی (درخواست مبلغ)
                if "payment_amount_prompt_id" in context.user_data:
                    try:
                        await context.bot.edit_message_reply_markup(
                            chat_id=update.effective_chat.id,
                            message_id=context.user_data["payment_amount_prompt_id"],
                            reply_markup=None
                        )
                    except Exception as e:
                        logger.error(f"خطا در حذف دکمه پیام قبلی مبلغ: {e}")
                
                # نمایش تأیید مبلغ
                formatted_amount = format_number_with_commas(amount)
                msg = await update.message.reply_text(
                    f"💰 تأیید مبلغ شارژ\n\n"
                    f"مبلغ وارد شده: {formatted_amount} تومان\n\n"
                    f"در صورت تأیید، روی دکمه «تأیید و پرداخت» کلیک کنید.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ تأیید و پرداخت", callback_data=f"confirm_payment^{amount}")],
                        [InlineKeyboardButton("❌ لغو", callback_data="cancel_payment^")]
                    ])
                )
                context.user_data["payment_confirm_prompt_id"] = msg.message_id
                
                # تنظیم وضعیت گفتگو
                context.user_data["payment_state"] = CONFIRM_AMOUNT
                
            except ValueError:
                await update.message.reply_text(
                    "❌ لطفاً یک عدد معتبر وارد کنید. (مثال: 50000)",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 تلاش مجدد", callback_data="payment_method^card")],
                        [InlineKeyboardButton("❌ لغو", callback_data="increasebalance^")]
                    ])
                )
            
            return
        
        elif payment_state == CONFIRM_AMOUNT:
            # این بخش توسط callback انجام می‌شود، اما اگر نیاز بود می‌توان اینجا هم مدیریت کرد
            pass
        
        elif payment_state == SEND_RECEIPT:
            # دریافت رسید پرداخت
            if update.message.photo:
                logger.info(f"دریافت عکس رسید پرداخت از کاربر {user_id}")
                try:
                    # دریافت عکس رسید
                    photo = update.message.photo[-1]  # بزرگترین نسخه عکس
                    file_id = photo.file_id
                    
                    # دریافت اطلاعات پرداخت
                    amount = user_payment_data.get(user_id, {}).get("amount", 0)
                    formatted_amount = format_number_with_commas(amount)
                    logger.info(f"ارسال عکس رسید پرداخت به کانال ادمین، مبلغ: {formatted_amount}")
                    
                    # ویرایش پیام قبلی (تأیید مبلغ)
                    if "payment_confirm_prompt_id" in context.user_data:
                        try:
                            await context.bot.edit_message_reply_markup(
                                chat_id=update.effective_chat.id,
                                message_id=context.user_data["payment_confirm_prompt_id"],
                                reply_markup=None
                            )
                        except Exception as e:
                            logger.error(f"خطا در حذف دکمه پیام قبلی تأیید مبلغ: {e}")
                    
                    # ارسال پیام تأیید به کاربر
                    await update.message.reply_text(
                        "✅ رسید پرداخت شما با موفقیت دریافت شد\n\n"
                        "پرداخت شما در حال بررسی توسط تیم پشتیبانی است و پس از تأیید، اعتبار به حساب شما افزوده خواهد شد.\n\n"
                        "این فرآیند معمولاً کمتر از 2 ساعت طول می‌کشد."
                    )
                    
                    # ارسال اطلاعات به کانال ادمین
                    caption = (
                        f"💰 درخواست افزایش اعتبار\n\n"
                        f"کاربر: {user_id}\n"
                        f"نام کاربری: @{update.effective_user.username or 'ندارد'}\n"
                        f"مبلغ درخواستی: {formatted_amount} تومان\n"
                        f"زمان: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}"
                    )
                    
                    # ارسال عکس به کانال ادمین
                    admin_message = await context.bot.send_photo(
                        chat_id=BOT_CONFIG["order-channel-id"],
                        photo=file_id,
                        caption=caption
                    )
                    
                    # دریافت شناسه پیام
                    message_id = admin_message.message_id
                    logger.info(f"شناسه پیام در کانال ادمین: {message_id}")
                    
                    # ثبت تراکنش در پایگاه داده
                    transaction_id = register_transaction(user_id, amount, file_id, message_id)
                    logger.info(f"تراکنش با شناسه {transaction_id} ثبت شد")
                    
                    # اضافه کردن دکمه‌های اینلاین به پیام
                    await context.bot.edit_message_reply_markup(
                        chat_id=BOT_CONFIG["order-channel-id"],
                        message_id=message_id,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ تأیید پرداخت", callback_data=f"admin_approve_payment^{user_id}^{amount}^{message_id}")],
                            [InlineKeyboardButton("🔄 تأیید با مبلغ دلخواه", url=f"https://t.me/{BOT_CONFIG['bot-username']}?start=custom_{user_id}_{message_id}")],
                            [InlineKeyboardButton("❌ رد پرداخت", url=f"https://t.me/{BOT_CONFIG['bot-username']}?start=reject_{user_id}_{message_id}")]
                        ])
                    )
                    
                    # پاک کردن اطلاعات موقت
                    if user_id in user_payment_data:
                        del user_payment_data[user_id]
                    context.user_data.pop("payment_state", None)
                    
                except Exception as e:
                    logger.error(f"خطا در پردازش رسید پرداخت: {e}")
                    await update.message.reply_text(
                        "❌ خطایی در پردازش رسید پرداخت رخ داد. لطفاً مجدداً تلاش کنید یا با پشتیبانی تماس بگیرید.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔄 تلاش مجدد", callback_data="payment_method^card")],
                            [InlineKeyboardButton("❌ لغو", callback_data="increasebalance^")]
                        ])
                    )
                
            else:
                # اگر عکس ارسال نشده باشد
                logger.warning(f"کاربر {user_id} پیام متنی به جای عکس رسید ارسال کرد")
                await update.message.reply_text(
                    "❌ لطفاً تصویر رسید پرداخت خود را به صورت عکس ارسال کنید.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ لغو", callback_data="increasebalance^")]
                    ])
                )
            
            return
    
    # پردازش دستورات معمولی
    if update.message.text:
        message_text = update.message.text
        
        if message_text.startswith('/start'):
            # اجرای دستور start که حالا پارامترها را نیز پردازش می‌کند
            await start(update, context)
        
        elif message_text.startswith('/admin'):
            await admin_command(update, context)
        
        elif "reject_payment" in context.user_data:
            # پردازش دلیل رد پرداخت
            reject_data = context.user_data["reject_payment"]
            user_id = reject_data["user_id"]
            message_id = reject_data["message_id"]
            reason = update.message.text
            
            # به‌روزرسانی وضعیت تراکنش
            update_transaction_status(message_id, "rejected", reason)
            
            # ارسال پیام به کاربر
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"❌ پرداخت شما رد شد.\n\n"
                         f"دلیل: {reason}\n\n"
                         f"در صورت نیاز به راهنمایی بیشتر با پشتیبانی تماس بگیرید."
                )
            except Exception as e:
                logger.error(f"خطا در ارسال پیام به کاربر: {e}")
            
            # به‌روزرسانی پیام در کانال ادمین
            await context.bot.edit_message_caption(
                chat_id=BOT_CONFIG["order-channel-id"],
                message_id=message_id,
                caption=f"❌ پرداخت رد شد\n\n"
                       f"کاربر: {user_id}\n"
                       f"دلیل: {reason}\n"
                       f"وضعیت: رد شده توسط ادمین",
                reply_markup=None
            )
            
            # ویرایش پیام قبلی (درخواست دلیل رد)
            if "prompt_message_id" in reject_data:
                try:
                    await context.bot.edit_message_text(
                        chat_id=update.effective_chat.id,
                        message_id=reject_data["prompt_message_id"],
                        text=f"✅ دلیل رد: {reason}",
                        reply_markup=None
                    )
                except Exception as e:
                    logger.error(f"خطا در ویرایش پیام قبلی: {e}")
            
            # پاک کردن اطلاعات موقت
            del context.user_data["reject_payment"]
            
            # ارسال پیام تأیید
            await update.message.reply_text(
                "✅ پیام رد پرداخت با موفقیت به کاربر ارسال شد.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("» بازگشت به منوی اصلی", callback_data="userpanel^")]
                ])
            )
        
        elif "custom_amount" in context.user_data:
            # پردازش مبلغ دلخواه
            custom_data = context.user_data["custom_amount"]
            user_id = custom_data["user_id"]
            message_id = custom_data["message_id"]
            
            try:
                # تبدیل مبلغ وارد شده به عدد
                amount_text = message_text.replace(",", "").replace("،", "").strip()
                amount = int(amount_text)
                
                # افزایش موجودی کاربر
                update_user_balance(user_id, amount)
                
                # به‌روزرسانی وضعیت تراکنش
                update_transaction_status(message_id, "approved_custom", f"مبلغ تأیید شده: {amount}")
                
                # ارسال پیام به کاربر
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"✅ پرداخت شما تأیید شد!\n\n"
                             f"مبلغ {format_number_with_commas(amount)} تومان به اعتبار شما افزوده شد."
                    )
                except Exception as e:
                    logger.error(f"خطا در ارسال پیام به کاربر: {e}")
                
                # به‌روزرسانی پیام در کانال ادمین
                await context.bot.edit_message_caption(
                    chat_id=BOT_CONFIG["order-channel-id"],
                    message_id=message_id,
                    caption=f"✅ پرداخت تأیید شد (با مبلغ دلخواه)\n\n"
                           f"کاربر: {user_id}\n"
                           f"مبلغ: {format_number_with_commas(amount)} تومان\n"
                           f"وضعیت: تأیید شده با مبلغ دلخواه",
                    reply_markup=None
                )
                
                # ویرایش پیام قبلی (درخواست مبلغ دلخواه)
                if "prompt_message_id" in custom_data:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id,
                            message_id=custom_data["prompt_message_id"],
                            text=f"✅ مبلغ تأیید شده: {format_number_with_commas(amount)} تومان",
                            reply_markup=None
                        )
                    except Exception as e:
                        logger.error(f"خطا در ویرایش پیام قبلی: {e}")
                
                # پاک کردن اطلاعات موقت
                del context.user_data["custom_amount"]
                
                # ارسال پیام تأیید
                await update.message.reply_text(
                    f"✅ مبلغ {format_number_with_commas(amount)} تومان با موفقیت به اعتبار کاربر افزوده شد.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("» بازگشت به منوی اصلی", callback_data="userpanel^")]
                    ])
                )
                
            except ValueError:
                await update.message.reply_text(
                    "❌ لطفاً یک عدد معتبر وارد کنید. (مثال: 50000)",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔄 تلاش مجدد", callback_data=f"admin_custom_amount^{user_id}^0^{message_id}")],
                        [InlineKeyboardButton("❌ لغو", callback_data="admin_panel^")]
                    ])
                )
        
        elif "awaiting_card_info" in context.user_data and context.user_data["awaiting_card_info"]:
            # فقط ادمین مجاز است
            if user_id != BOT_CONFIG["admin-username"]:
                await update.message.reply_text("شما دسترسی به این بخش را ندارید!")
                context.user_data.pop("awaiting_card_info", None)
                return
            # دریافت و اعتبارسنجی ورودی
            parts = update.message.text.split(",")
            if len(parts) == 2:
                card_number = parts[0].strip()
                card_holder = parts[1].strip()
                BOT_CONFIG["card_number"] = card_number
                BOT_CONFIG["card_holder"] = card_holder
                set_card_info(card_number, card_holder)
                context.user_data.pop("awaiting_card_info", None)
                await update.message.reply_text(
                    f"✅ شماره کارت و نام صاحب کارت با موفقیت به‌روزرسانی شد!\n\nشماره کارت جدید: {card_number}\nبه نام: {card_holder}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("» بازگشت به پنل ادمین", callback_data="admin_panel^")]
                    ])
                )
            else:
                await update.message.reply_text(
                    "❌ فرمت ورودی صحیح نیست! لطفاً به صورت زیر وارد کنید:\n6037991521965867, محمد امین چهاردولی",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("» بازگشت به پنل ادمین", callback_data="admin_panel^")]
                    ])
                )
            return
        
        else:
            # پاسخ به پیام‌های نامشخص
            await update.message.reply_text("متوجه نشدم چی گفتی! لطفاً دوباره تلاش کنید. 🤔")

# تابع اصلی
def main():
    # ایجاد پایگاه داده
    setup_database()
    
    # خواندن شماره کارت و نام صاحب کارت از دیتابیس در صورت وجود
    card_info = get_card_info()
    if card_info:
        BOT_CONFIG["card_number"] = card_info["card_number"]
        BOT_CONFIG["card_holder"] = card_info["card_holder"]
    
    # ایجاد اپلیکیشن
    application = Application.builder().token(BOT_CONFIG["TOKEN"]).build()
    
    # اضافه کردن هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(button_click))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))
    
    # شروع پولینگ
    logger.info(f"ربات {BOT_CONFIG['bot-name']} شروع به کار کرد...")
    application.run_polling()

if __name__ == "__main__":
    main() 