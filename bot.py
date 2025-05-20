import logging
import os
import io
import json
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
from datetime import datetime, timedelta
import time
import uuid
import re
import arabic_reshaper
from bidi.algorithm import get_display
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import jdatetime
from matplotlib import font_manager
import PyPDF2
import fitz  # PyMuPDF
import docx
import pptx

# ماژول‌های داخلی
from config import BOT_CONFIG, DB_CONFIG
from database import (setup_database, check_user_exists, register_user, get_user_profile, 
                     register_referral, update_user_balance, update_user_phone, get_card_info, 
                     set_card_info, get_stats, get_top_inviters, get_usernames,
                     get_referrals_by_inviter, get_top_inviter_by_amount,
                     get_top_inviter_by_count, get_total_referral_rewards,
                     get_growth_chart, get_all_users, register_transaction,
                     update_transaction_status, get_transaction_by_message_id, 
                     get_user_transactions, get_loyal_users,
                     get_print_prices, update_print_prices, save_user_address,
                     get_user_addresses, register_print_order, update_print_order_status,
                     get_user_print_orders, get_print_order_details, get_all_print_orders,
                     check_user_info_exists)

# تنظیم لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# مسیر پایگاه داده
DB_PATH = DB_CONFIG["db_path"]

# مراحل گفتگو برای افزایش موجودی
PAYMENT_METHOD, ENTER_AMOUNT, CONFIRM_AMOUNT, SEND_RECEIPT = range(4)

# مراحل گفتگو برای درخواست پرینت
(UPLOAD_FILE, EXTRACT_PAGES, SELECT_PAGE_RANGE, SELECT_PRINT_TYPE, 
 SELECT_PRINT_METHOD, SELECT_PAPER_SIZE, SELECT_PAPER_TYPE, 
 SELECT_STAPLE, ENTER_DESCRIPTION, SELECT_DELIVERY_TYPE, 
 ENTER_FULLNAME, ENTER_PHONE, SELECT_ADDRESS, ENTER_NEW_ADDRESS, 
 CONFIRM_ORDER, PROCESS_PAYMENT) = range(16)

# ذخیره اطلاعات موقت کاربر
user_payment_data = {}
user_print_data = {}

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
                [InlineKeyboardButton("درخواست پرینت یا کپی", callback_data="print_request^")],
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
        msg += f"📊 مجموع کل دعوت‌ها: {stats['total_referrals']}\n"
        msg += f"• دعوت‌های امروز: {stats['today_referrals']}\n"
        msg += f"• دعوت‌های دیروز: {stats['yesterday_referrals']}\n"
        msg += f"• دعوت‌های هفته جاری: {stats['week_referrals']}\n\n"
        msg += f"🎁 مجموع پاداش پرداختی:\n  - دعوت‌کنندگان: {format_number_with_commas(total_inviter)} تومان\n  - دعوت‌شونده‌ها: {format_number_with_commas(total_invitee)} تومان\n  - مجموع: {format_number_with_commas(total_inviter + total_invitee)} تومان\n\n"
        if top_amount:
            msg += f"🏆 بیشترین درآمد از دعوت: @{top_amount[1] or 'بدون_نام'} ({top_amount[0]}) با {format_number_with_commas(top_amount[2])} تومان\n"
        if top_count:
            msg += f"👑 بیشترین دعوت موفق: @{top_count[1] or 'بدون_نام'} ({top_count[0]}) با {top_count[2]} دعوت\n"
        msg += "\nبرترین دعوت‌کنندگان بر اساس تعداد دعوت:\n"
        for idx, (uid, count) in enumerate(top_inviters[:5], 1):
            uname = usernames.get(uid, "بدون نام کاربری")
            msg += f"{idx}. {uname} ({uid}) - {count} دعوت موفق\n"
        # برترین دعوت‌کنندگان بر اساس مبلغ دریافتی
        # دریافت ۵ نفر برتر بر اساس مبلغ
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.username, SUM(r.inviter_cart_amount) as total_amount
            FROM referrals r
            JOIN users u ON r.inviter_user_id = u.user_id
            GROUP BY r.inviter_user_id
            ORDER BY total_amount DESC
            LIMIT 5
        ''')
        top_by_amount = cursor.fetchall()
        conn.close()
        if top_by_amount:
            msg += "\nبرترین دعوت‌کنندگان بر اساس مبلغ دریافتی:\n"
            for idx, (uid, uname, amount) in enumerate(top_by_amount, 1):
                msg += f"{idx}. @{uname or 'بدون_نام'} ({uid}) - {format_number_with_commas(amount)} تومان\n"
        buttons = []
        for idx, (uid, count) in enumerate(top_inviters[:5], 1):
            uname = usernames.get(uid, "بدون نام کاربری")
            buttons.append([InlineKeyboardButton(f"جزئیات دعوت‌های {uname}", callback_data=f"referral_details^{uid}")])
        buttons.append([InlineKeyboardButton("» بازگشت به آمار", callback_data="admin_stats^")])
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(buttons)
        )

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
        
        # آمار کاربران جدید
        msg += "👤 آمار کاربران جدید:\n"
        msg += f"• کاربران امروز: {stats['today_users']} کاربر\n"
        msg += f"• کاربران دیروز: {stats['yesterday_users']} کاربر\n"
        msg += f"• کاربران هفته جاری: {stats['week_users']} کاربر\n"
        msg += f"• کاربران هفته گذشته: {stats['last_week_users']} کاربر\n"
        msg += f"• کاربران ماه گذشته: {stats['month_users']} کاربر\n"
        msg += f"• کل کاربران: {stats['total_users']} کاربر\n\n"
        
        # آمار کاربران فعال
        msg += "🔵 آمار کاربران فعال:\n"
        msg += f"• کاربران فعال امروز: {stats['active_today']} کاربر\n"
        msg += f"• کاربران فعال دیروز: {stats['active_yesterday']} کاربر\n"
        msg += f"• کاربران فعال هفته جاری: {stats['active_week']} کاربر\n\n"
        
        # آمار کاربران دعوت شده
        msg += "🤝 آمار کاربران دعوت شده:\n"
        msg += f"• دعوت‌های امروز: {stats['today_referrals']} دعوت\n"
        msg += f"• دعوت‌های دیروز: {stats['yesterday_referrals']} دعوت\n"
        msg += f"• دعوت‌های هفته جاری: {stats['week_referrals']} دعوت\n"
        msg += f"• کل دعوت‌ها: {stats['total_referrals']} دعوت\n\n"
        
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
        
        # آمار موجودی کاربران
        msg += "💵 موجودی کاربران:\n"
        msg += f"• مجموع موجودی کل کاربران: {format_number_with_commas(stats['total_balance'])} تومان\n\n"
        
        # آمار پاداش‌های رفرال
        total_inviter, total_invitee = get_total_referral_rewards()
        msg += "🎁 پاداش‌های رفرال:\n"
        msg += f"• مجموع پاداش دعوت‌کنندگان: {format_number_with_commas(total_inviter)} تومان\n"
        msg += f"• مجموع پاداش دعوت‌شوندگان: {format_number_with_commas(total_invitee)} تومان\n"
        msg += f"• مجموع کل پاداش‌ها: {format_number_with_commas(total_inviter + total_invitee)} تومان\n\n"
        
        # آمار تراکنش‌ها (اضافه کردن کوئری برای دریافت آمار تراکنش‌ها)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # تعداد تراکنش‌های موفق
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'approved'")
        successful_transactions = cursor.fetchone()[0]
        
        # مجموع مبلغ تراکنش‌های موفق
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE status = 'approved'")
        total_successful_amount = cursor.fetchone()[0] or 0
        
        # تعداد تراکنش‌های در انتظار
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'pending'")
        pending_transactions = cursor.fetchone()[0]
        
        # مجموع مبلغ تراکنش‌های در انتظار
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE status = 'pending'")
        total_pending_amount = cursor.fetchone()[0] or 0
        
        # تراکنش‌های امروز
        today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        cursor.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE status = 'approved' AND created_at >= ?", (today_start,))
        result = cursor.fetchone()
        today_transactions = result[0]
        today_amount = result[1] or 0
        
        conn.close()
        
        msg += "💳 آمار تراکنش‌ها:\n"
        msg += f"• تراکنش‌های موفق امروز: {today_transactions} تراکنش ({format_number_with_commas(today_amount)} تومان)\n"
        msg += f"• کل تراکنش‌های موفق: {successful_transactions} تراکنش ({format_number_with_commas(total_successful_amount)} تومان)\n"
        msg += f"• تراکنش‌های در انتظار: {pending_transactions} تراکنش ({format_number_with_commas(total_pending_amount)} تومان)\n"
        
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("» بازگشت به آمار", callback_data="admin_stats^")]
            ])
        )
        return

    elif callback_data == "admin_stats_behavior^" and user_id == BOT_CONFIG["admin-username"]:
        stats = get_stats()
        
        # دریافت کاربران وفادار (کاربرانی که در حداقل 2 هفته مختلف تراکنش داشته‌اند)
        loyal_users = get_loyal_users(min_weeks=2)
        
        # دریافت اطلاعات تکمیلی از دیتابیس
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # تعداد کاربران با شماره تلفن ثبت شده
        cursor.execute("SELECT COUNT(*) FROM users WHERE phone_number != ''")
        users_with_phone = cursor.fetchone()[0]
        
        # درصد کاربران با شماره تلفن
        phone_percentage = round((users_with_phone / stats['total_users']) * 100 if stats['total_users'] > 0 else 0, 1)
        
        # تعداد کاربران با حداقل یک تراکنش
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM transactions")
        users_with_transaction = cursor.fetchone()[0]
        
        # درصد کاربران با حداقل یک تراکنش
        transaction_percentage = round((users_with_transaction / stats['total_users']) * 100 if stats['total_users'] > 0 else 0, 1)
        
        # میانگین تعداد تراکنش به ازای هر کاربر
        cursor.execute("SELECT COUNT(*) FROM transactions")
        total_transactions = cursor.fetchone()[0]
        avg_transactions_per_user = round(total_transactions / users_with_transaction if users_with_transaction > 0 else 0, 1)
        
        # میانگین موجودی کاربران
        avg_balance = round(stats['total_balance'] / stats['total_users'] if stats['total_users'] > 0 else 0)
        
        conn.close()
        
        msg = "👤 آمار رفتار کاربران\n\n"
        
        # آمار کلی رفتار کاربران
        msg += "📊 رفتار عمومی کاربران:\n"
        msg += f"• کاربران با شماره تلفن: {users_with_phone} کاربر ({phone_percentage}%)\n"
        msg += f"• کاربران با حداقل یک تراکنش: {users_with_transaction} کاربر ({transaction_percentage}%)\n"
        msg += f"• میانگین تعداد تراکنش هر کاربر: {avg_transactions_per_user} تراکنش\n"
        msg += f"• میانگین موجودی کاربران: {format_number_with_commas(avg_balance)} تومان\n\n"
        
        # آمار کاربران وفادار
        msg += "🔄 کاربران وفادار (فعال در حداقل ۲ هفته):\n"
        msg += f"• تعداد کاربران وفادار: {len(loyal_users)} کاربر\n"
        if loyal_users:
            # نمایش 5 کاربر وفادار برتر
            user_ids = [uid for uid, _ in loyal_users[:5]]
            usernames = get_usernames(user_ids)
            msg += "• کاربران وفادار برتر:\n"
            for i, (uid, weeks) in enumerate(loyal_users[:5], 1):
                uname = usernames.get(uid, "بدون نام کاربری")
                msg += f"  {i}. {uname} ({uid}) - فعال در {weeks} هفته\n"
        
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
        import matplotlib  # اضافه کردن ایمپورت برای رفع خطا
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

    elif callback_data == "print_request^":
        # شروع فرآیند درخواست پرینت
        await query.edit_message_text(
            "📄 درخواست پرینت یا کپی\n\n"
            "لطفاً فایل مورد نظر خود را برای پرینت ارسال کنید.\n"
            "فرمت‌های قابل قبول: PDF, Word (docx), PowerPoint (pptx), تصاویر (jpg, png)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
            ])
        )
        
        # تنظیم وضعیت گفتگو
        context.user_data["print_state"] = UPLOAD_FILE
        
        # پاک کردن داده‌های قبلی اگر وجود داشته باشد
        if user_id in user_print_data:
            del user_print_data[user_id]
        
        # ایجاد دیکشنری جدید برای ذخیره اطلاعات سفارش
        user_print_data[user_id] = {
            "file_ids": [],
            "file_paths": [],
            "file_type": None,
            "page_count": 0,
            "images_count": 0
        }

    # --- فرآیند پرینت ---
    elif callback_data.startswith('page_range^'):
        if callback_data == 'page_range^all':
            user_print_data[user_id]['page_range'] = 'all'
            await query.edit_message_text(
                "لطفاً نوع چاپ را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("سیاه و سفید", callback_data="print_type^bw")],
                    [InlineKeyboardButton("رنگی", callback_data="print_type^color")],
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                ])
            )
            context.user_data["print_state"] = SELECT_PRINT_TYPE
        elif callback_data == 'page_range^custom':
            await query.edit_message_text(
                "لطفاً محدوده صفحات مورد نظر را به صورت مثال زیر وارد کنید:\nمثال: 1-5,7,9-12",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                ])
            )
            context.user_data["print_state"] = SELECT_PAGE_RANGE

    elif callback_data.startswith('print_type^'):
        print_type = callback_data.split('^')[1]
        user_print_data[user_id]['print_type'] = print_type
        await query.edit_message_text(
            "لطفاً روش چاپ را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("یک رو", callback_data="print_method^single")],
                [InlineKeyboardButton("دو رو", callback_data="print_method^double")],
                [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
            ])
        )
        context.user_data["print_state"] = SELECT_PRINT_METHOD

    elif callback_data.startswith('print_method^'):
        print_method = callback_data.split('^')[1]
        user_print_data[user_id]['print_method'] = print_method
        # منوی انتخاب اندازه کاغذ
        await query.edit_message_text(
            "لطفاً اندازه کاغذ را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("A4", callback_data="paper_size^a4"), InlineKeyboardButton("A5", callback_data="paper_size^a5"), InlineKeyboardButton("A3", callback_data="paper_size^a3")],
                [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
            ])
        )
        context.user_data["print_state"] = SELECT_PAPER_SIZE

    elif callback_data.startswith('paper_size^'):
        paper_size = callback_data.split('^')[1]
        user_print_data[user_id]['paper_size'] = paper_size
        # منوی انتخاب نوع کاغذ با توجه به محدودیت‌ها
        paper_type_buttons = [[InlineKeyboardButton("معمولی", callback_data="paper_type^normal")]]
        if paper_size != 'a5':
            paper_type_buttons.append([InlineKeyboardButton("گلاسه 175 گرمی", callback_data="paper_type^glossy_175")])
            paper_type_buttons.append([InlineKeyboardButton("گلاسه 250 گرمی", callback_data="paper_type^glossy_250")])
        paper_type_buttons.append([InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")])
        await query.edit_message_text(
            "لطفاً نوع کاغذ را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(paper_type_buttons)
        )
        context.user_data["print_state"] = SELECT_PAPER_TYPE

    elif callback_data.startswith('paper_type^'):
        paper_type = callback_data.split('^')[1]
        user_print_data[user_id]['paper_type'] = paper_type
        await query.edit_message_text(
            "آیا نیاز به منگنه دارد؟",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("بله", callback_data="staple^yes"), InlineKeyboardButton("خیر", callback_data="staple^no")],
                [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
            ])
        )
        context.user_data["print_state"] = SELECT_STAPLE

    elif callback_data.startswith('staple^'):
        staple = callback_data.split('^')[1] == 'yes'
        user_print_data[user_id]['staple'] = staple
        await query.edit_message_text(
            "لطفاً توضیحات سفارش (اختیاری) را وارد کنید یا فقط یک پیام خالی ارسال کنید:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
            ])
        )
        context.user_data["print_state"] = ENTER_DESCRIPTION

    elif callback_data.startswith('delivery_type^'):
        delivery_type = callback_data.split('^')[1]
        user_print_data[user_id]['delivery_type'] = delivery_type
        if delivery_type == 'in_person':
            user_info = check_user_info_exists(user_id)
            if user_info:
                user_print_data[user_id]["full_name"] = user_info["full_name"]
                user_print_data[user_id]["phone_number"] = user_info["phone_number"]
                await query.edit_message_text(
                    f"اطلاعات قبلی شما:\n\n👤 نام و نام خانوادگی: {user_info['full_name']}\n📱 شماره تماس: {user_info['phone_number']}\n\nآیا می‌خواهید از همین اطلاعات استفاده کنید؟",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ بله، همین اطلاعات", callback_data="use_previous_info^yes")],
                        [InlineKeyboardButton("❌ خیر، اطلاعات جدید", callback_data="use_previous_info^no")],
                        [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                    ])
                )
            else:
                await query.edit_message_text(
                    "لطفاً نام و نام خانوادگی خود را وارد کنید:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                    ])
                )
                context.user_data["print_state"] = ENTER_FULLNAME
        else:
            await query.edit_message_text(
                "لطفاً شماره تماس خود را وارد کنید:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                ])
            )
            context.user_data["print_state"] = ENTER_PHONE

    elif callback_data.startswith('select_address^'):
        address_id = callback_data.split('^')[1]
        if address_id == 'new':
            await query.edit_message_text(
                "لطفاً آدرس جدید خود را وارد کنید:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                ])
            )
            context.user_data["print_state"] = ENTER_NEW_ADDRESS
        else:
            addresses = get_user_addresses(user_id)
            address = next((a['address'] for a in addresses if str(a['id']) == address_id), None)
            user_print_data[user_id]['address'] = address
            await show_order_confirmation(update, context, user_id)
            context.user_data["print_state"] = CONFIRM_ORDER

    elif callback_data.startswith('more_images^'):
        more = callback_data.split('^')[1]
        if more == 'yes':
            await query.edit_message_text(
                "لطفاً تصویر بعدی را ارسال کنید:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                ])
            )
            context.user_data["print_state"] = UPLOAD_FILE
        else:
            await query.edit_message_text(
                "لطفاً نوع چاپ را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("سیاه و سفید", callback_data="print_type^bw")],
                    [InlineKeyboardButton("رنگی", callback_data="print_type^color")],
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                ])
            )
            context.user_data["print_state"] = SELECT_PRINT_TYPE

    elif callback_data.startswith('use_previous_info^'):
        use_prev = callback_data.split('^')[1]
        if use_prev == 'yes':
            await show_order_confirmation(update, context, user_id)
            context.user_data["print_state"] = CONFIRM_ORDER
        else:
            await query.edit_message_text(
                "لطفاً نام و نام خانوادگی خود را وارد کنید:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                ])
            )
            context.user_data["print_state"] = ENTER_FULLNAME

    elif callback_data.startswith('confirm_order^'):
        confirm_type = callback_data.split('^')[1]
        print_data = user_print_data.get(user_id, {})
        total_price = print_data.get('total_price', 0)
        user_profile = get_user_profile(user_id)
        user_balance = user_profile.get('balance', 0)
        if confirm_type == 'balance' and user_balance >= total_price:
            update_user_balance(user_id, -total_price)
            order_id = register_print_order(
                user_id,
                ','.join(print_data.get('file_ids', [])),
                print_data.get('file_type'),
                print_data.get('page_count', 0),
                print_data.get('page_range', ''),
                print_data.get('print_type', ''),
                print_data.get('print_method', ''),
                print_data.get('paper_size', ''),
                print_data.get('paper_type', ''),
                int(print_data.get('staple', False)),
                print_data.get('delivery_type', ''),
                print_data.get('full_name', ''),
                print_data.get('phone_number', ''),
                print_data.get('address', ''),
                print_data.get('description', ''),
                total_price
            )
            await query.edit_message_text("✅ سفارش شما با موفقیت ثبت شد و در حال پردازش است.")
            
            # ارسال به کانال ادمین
            logger.info(f"ارسال سفارش به کانال ادمین با شناسه {order_id}")
            caption = f"سفارش جدید پرینت\n\nشناسه سفارش: {order_id}\nنام: {print_data.get('full_name','')}\nشماره: {print_data.get('phone_number','')}\nنوع چاپ: {print_data.get('print_type','')}\nروش: {print_data.get('print_method','')}\nکاغذ: {print_data.get('paper_type','')}\nاندازه: {print_data.get('paper_size','')}\nتعداد صفحات/عکس: {print_data.get('page_count', print_data.get('images_count',0))}\nمنگنه: {'دارد' if print_data.get('staple') else 'ندارد'}\nتحویل: {print_data.get('delivery_type','')}\nآدرس: {print_data.get('address','')}\nتوضیحات: {print_data.get('description','')}\nمبلغ: {total_price} تومان"
            
            try:
                # ارسال اطلاعات سفارش به کانال ادمین
                admin_channel_id = BOT_CONFIG.get("order-channel-id")
                if admin_channel_id:
                    logger.info(f"ارسال اطلاعات سفارش به کانال ادمین: {admin_channel_id}")
                    
                    # ارسال فایل‌ها
                    file_ids = print_data.get('file_ids', [])
                    logger.info(f"تعداد فایل‌ها برای ارسال: {len(file_ids)}")
                    
                    for idx, file_id in enumerate(file_ids):
                        try:
                            file_caption = caption if idx == 0 else f"فایل {idx+1} از سفارش {order_id}"
                            logger.info(f"ارسال فایل با شناسه {file_id} به کانال ادمین")
                            
                            if print_data.get('file_type') == 'image':
                                await context.bot.send_photo(
                                    chat_id=admin_channel_id,
                                    photo=file_id,
                                    caption=file_caption
                                )
                            else:
                                await context.bot.send_document(
                                    chat_id=admin_channel_id,
                                    document=file_id,
                                    caption=file_caption
                                )
                            logger.info(f"فایل با شناسه {file_id} با موفقیت به کانال ادمین ارسال شد")
                        except Exception as e:
                            logger.error(f"خطا در ارسال فایل {idx+1} به کانال ادمین: {str(e)}")
                else:
                    logger.error("شناسه کانال ادمین تنظیم نشده است")
            except Exception as e:
                logger.error(f"خطا در ارسال سفارش به کانال ادمین: {str(e)}")
            
            # پاکسازی داده‌های سفارش
            user_print_data.pop(user_id, None)
            context.user_data.pop("print_state", None)
        elif confirm_type == 'increase':
            await query.edit_message_text(
                f"برای پرداخت مبلغ {total_price - user_balance} تومان، لطفاً افزایش موجودی دهید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("افزایش موجودی", callback_data="increasebalance^")],
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                ])
            )
        elif confirm_type == 'partial' and user_balance > 0:
            # هدایت به پرداخت کسری
            await query.edit_message_text(
                f"شما {user_balance} تومان اعتبار دارید. لطفاً {total_price - user_balance} تومان دیگر پرداخت کنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("افزایش موجودی", callback_data="increasebalance^")],
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
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
    
    # بررسی وضعیت گفتگو برای درخواست پرینت
    if "print_state" in context.user_data:
        print_state = context.user_data["print_state"]
        logger.info(f"وضعیت درخواست پرینت کاربر {user_id}: {print_state}")
        
        if print_state == UPLOAD_FILE:
            # دریافت فایل برای پرینت
            if update.message.document:
                # دریافت فایل سند
                document = update.message.document
                file_id = document.file_id
                mime_type = document.mime_type
                file_name = document.file_name or "unknown"
                file_extension = os.path.splitext(file_name)[1].lower() if file_name else ""
                
                # بررسی نوع فایل
                valid_extensions = ['.pdf', '.docx', '.pptx']
                if file_extension not in valid_extensions:
                    await update.message.reply_text(
                        "❌ فرمت فایل پشتیبانی نمی‌شود. لطفاً یک فایل PDF، Word یا PowerPoint ارسال کنید.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                        ])
                    )
                    return
                
                # دانلود فایل
                file_path = await download_telegram_file(context, file_id)
                if not file_path:
                    await update.message.reply_text(
                        "❌ خطا در دانلود فایل. لطفاً مجدداً تلاش کنید.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                        ])
                    )
                    return
                
                # استخراج نوع فایل و تعداد صفحات
                file_type, page_count = await get_file_pages(file_path)
                
                if page_count == 0:
                    await update.message.reply_text(
                        "❌ خطا در استخراج تعداد صفحات فایل. لطفاً فایل دیگری ارسال کنید.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                        ])
                    )
                    return
                
                # ذخیره اطلاعات فایل
                user_print_data[user_id]["file_ids"].append(file_id)
                user_print_data[user_id]["file_paths"].append(file_path)
                user_print_data[user_id]["file_type"] = file_type
                user_print_data[user_id]["page_count"] = page_count
                
                # نمایش اطلاعات فایل و درخواست محدوده صفحات
                await update.message.reply_text(
                    f"✅ فایل با موفقیت دریافت شد!\n\n"
                    f"📄 نوع فایل: {file_type.upper()}\n"
                    f"📊 تعداد صفحات: {page_count}\n\n"
                    f"لطفاً محدوده صفحات مورد نظر برای پرینت را مشخص کنید:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("همه صفحات", callback_data=f"page_range^all")],
                        [InlineKeyboardButton("انتخاب محدوده", callback_data=f"page_range^custom")],
                        [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                    ])
                )
                
                # تنظیم وضعیت گفتگو
                context.user_data["print_state"] = SELECT_PAGE_RANGE
                
            elif update.message.photo:
                # دریافت عکس
                photo = update.message.photo[-1]  # بزرگترین نسخه عکس
                file_id = photo.file_id
                
                # دانلود فایل
                file_path = await download_telegram_file(context, file_id, f"{uuid.uuid4()}.jpg")
                if not file_path:
                    await update.message.reply_text(
                        "❌ خطا در دانلود تصویر. لطفاً مجدداً تلاش کنید.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                        ])
                    )
                    return
                
                # ذخیره اطلاعات فایل
                user_print_data[user_id]["file_ids"].append(file_id)
                user_print_data[user_id]["file_paths"].append(file_path)
                user_print_data[user_id]["file_type"] = "image"
                user_print_data[user_id]["images_count"] += 1
                
                # پرسیدن آیا عکس دیگری هست
                await update.message.reply_text(
                    f"✅ تصویر با موفقیت دریافت شد! (تعداد: {user_print_data[user_id]['images_count']})\n\n"
                    f"آیا تصویر دیگری برای پرینت دارید؟",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ بله، عکس دیگری دارم", callback_data="more_images^yes")],
                        [InlineKeyboardButton("❌ خیر، ادامه بده", callback_data="more_images^no")],
                        [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                    ])
                )
                
            else:
                # اگر نوع فایل پشتیبانی نشده باشد
                await update.message.reply_text(
                    "❌ لطفاً یک فایل (PDF، Word، PowerPoint) یا تصویر ارسال کنید.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                    ])
                )
            
            return
        
        elif print_state == SELECT_PAGE_RANGE and update.message.text:
            # دریافت محدوده صفحات سفارشی
            try:
                page_range = update.message.text.strip()
                
                # اعتبارسنجی فرمت محدوده صفحات
                if not re.match(r'^(\d+(-\d+)?)(,\s*\d+(-\d+)?)*$', page_range):
                    raise ValueError("فرمت نامعتبر")
                
                # ذخیره محدوده صفحات
                user_print_data[user_id]["page_range"] = page_range
                
                # ادامه به مرحله بعدی (انتخاب نوع چاپ)
                await update.message.reply_text(
                    "لطفاً نوع چاپ را انتخاب کنید:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("سیاه و سفید", callback_data="print_type^bw")],
                        [InlineKeyboardButton("رنگی", callback_data="print_type^color")],
                        [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                    ])
                )
                
                # تنظیم وضعیت گفتگو
                context.user_data["print_state"] = SELECT_PRINT_TYPE
                
            except ValueError:
                await update.message.reply_text(
                    "❌ فرمت محدوده صفحات نامعتبر است. لطفاً به صورت اعداد جدا شده با کاما یا محدوده (مثال: 1-5,7,9-12) وارد کنید.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                    ])
                )
            
            return
        
        elif print_state == ENTER_DESCRIPTION:
            # دریافت توضیحات سفارش
            description = update.message.text
            user_print_data[user_id]["description"] = description
            
            # بررسی آیا ارسال با پیک فعال است
            prices = get_print_prices()
            delivery_enabled = prices.get('delivery_enabled', False) if prices else False
            
            if delivery_enabled:
                # نمایش گزینه‌های نوع تحویل
                await update.message.reply_text(
                    "لطفاً نوع تحویل سفارش را انتخاب کنید:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("تحویل حضوری", callback_data="delivery_type^in_person")],
                        [InlineKeyboardButton("ارسال با پیک", callback_data="delivery_type^delivery")],
                        [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                    ])
                )
            else:
                # اگر ارسال با پیک غیرفعال باشد، مستقیماً به حالت تحویل حضوری برو
                user_print_data[user_id]["delivery_type"] = "in_person"
                
                # بررسی وجود اطلاعات کاربر
                user_info = check_user_info_exists(user_id)
                
                if user_info:
                    # اگر اطلاعات کاربر موجود باشد، آنها را نمایش بده و بپرس آیا همان اطلاعات استفاده شود
                    user_print_data[user_id]["full_name"] = user_info["full_name"]
                    user_print_data[user_id]["phone_number"] = user_info["phone_number"]
                    
                    await update.message.reply_text(
                        f"اطلاعات قبلی شما:\n\n"
                        f"👤 نام و نام خانوادگی: {user_info['full_name']}\n"
                        f"📱 شماره تماس: {user_info['phone_number']}\n\n"
                        f"آیا می‌خواهید از همین اطلاعات استفاده کنید؟",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ بله، همین اطلاعات", callback_data="use_previous_info^yes")],
                            [InlineKeyboardButton("❌ خیر، اطلاعات جدید", callback_data="use_previous_info^no")],
                            [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                        ])
                    )
                else:
                    # اگر اطلاعات کاربر موجود نباشد، درخواست نام و نام خانوادگی
                    await update.message.reply_text(
                        "لطفاً نام و نام خانوادگی خود را وارد کنید:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                        ])
                    )
                    
                    # تنظیم وضعیت گفتگو
                    context.user_data["print_state"] = ENTER_FULLNAME
            
            # تنظیم وضعیت گفتگو
            if delivery_enabled:
                context.user_data["print_state"] = SELECT_DELIVERY_TYPE
            
            return
        
        elif print_state == ENTER_FULLNAME:
            # دریافت نام و نام خانوادگی
            full_name = update.message.text
            user_print_data[user_id]["full_name"] = full_name
            
            # درخواست شماره تماس
            await update.message.reply_text(
                "لطفاً شماره تماس خود را وارد کنید:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                ])
            )
            
            # تنظیم وضعیت گفتگو
            context.user_data["print_state"] = ENTER_PHONE
            
            return
        
        elif print_state == ENTER_PHONE:
            # دریافت شماره تماس
            phone_number = update.message.text
            
            # اعتبارسنجی شماره تماس
            if not re.match(r'^(0|\+98)?9\d{9}$', phone_number):
                await update.message.reply_text(
                    "❌ شماره تماس وارد شده نامعتبر است. لطفاً یک شماره موبایل معتبر وارد کنید.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                    ])
                )
                return
            
            # ذخیره شماره تماس
            user_print_data[user_id]["phone_number"] = phone_number
            
            # اگر نوع تحویل پیک باشد، درخواست آدرس
            if user_print_data[user_id].get("delivery_type") == "delivery":
                # بررسی وجود آدرس‌های قبلی
                addresses = get_user_addresses(user_id)
                
                if addresses:
                    # نمایش آدرس‌های قبلی
                    keyboard = []
                    for i, address in enumerate(addresses, 1):
                        keyboard.append([InlineKeyboardButton(f"آدرس {i}", callback_data=f"select_address^{address['id']}")])
                    
                    keyboard.append([InlineKeyboardButton("➕ آدرس جدید", callback_data="select_address^new")])
                    keyboard.append([InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")])
                    
                    # ساخت متن آدرس‌ها
                    address_text = "آدرس‌های قبلی شما:\n\n"
                    for i, address in enumerate(addresses, 1):
                        address_text += f"{i}- {address['address']}\n\n"
                    
                    address_text += "لطفاً یکی از آدرس‌های بالا را انتخاب کنید یا آدرس جدید وارد کنید:"
                    
                    await update.message.reply_text(
                        address_text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    
                    # تنظیم وضعیت گفتگو
                    context.user_data["print_state"] = SELECT_ADDRESS
                else:
                    # درخواست آدرس جدید
                    await update.message.reply_text(
                        "لطفاً آدرس دقیق خود را برای ارسال با پیک وارد کنید:",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
                        ])
                    )
                    
                    # تنظیم وضعیت گفتگو
                    context.user_data["print_state"] = ENTER_NEW_ADDRESS
            else:
                # اگر نوع تحویل حضوری باشد، به مرحله تأیید نهایی برو
                await show_order_confirmation(update, context, user_id)
                
                # تنظیم وضعیت گفتگو
                context.user_data["print_state"] = CONFIRM_ORDER
            
            return
        
        elif print_state == ENTER_NEW_ADDRESS:
            # دریافت آدرس جدید
            address = update.message.text
            
            # ذخیره آدرس در دیتابیس
            address_id = save_user_address(user_id, address)
            
            # ذخیره آدرس در اطلاعات سفارش
            user_print_data[user_id]["address"] = address
            
            # نمایش تأیید نهایی سفارش
            await show_order_confirmation(update, context, user_id)
            
            # تنظیم وضعیت گفتگو
            context.user_data["print_state"] = CONFIRM_ORDER
            
            return
    
    # بررسی وضعیت گفتگو برای افزایش موجودی
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

# تابع برای دانلود فایل از تلگرام
async def download_telegram_file(context, file_id, custom_filename=None):
    try:
        logger.info(f"شروع دانلود فایل با شناسه {file_id}")
        file = await context.bot.get_file(file_id)
        file_path = file.file_path
        logger.info(f"مسیر فایل در تلگرام: {file_path}")
        
        # ایجاد نام فایل منحصر به فرد
        if custom_filename:
            filename = custom_filename
        else:
            original_filename = os.path.basename(file_path)
            filename = f"{uuid.uuid4()}_{original_filename}"
        
        # ایجاد دایرکتوری برای ذخیره فایل‌ها
        os.makedirs('uploads', exist_ok=True)
        local_file_path = os.path.join('uploads', filename)
        logger.info(f"ذخیره فایل در مسیر محلی: {local_file_path}")
        
        # دانلود فایل
        await file.download_to_drive(local_file_path)
        logger.info(f"فایل با موفقیت دانلود شد: {local_file_path}")
        
        return local_file_path
    except Exception as e:
        logger.error(f"خطا در دانلود فایل: {e}")
        return None

# تابع برای استخراج تعداد صفحات از فایل PDF
async def extract_pdf_pages(file_path):
    try:
        logger.info(f"استخراج تعداد صفحات PDF از فایل: {file_path}")
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            pages = len(pdf_reader.pages)
            logger.info(f"تعداد صفحات PDF: {pages}")
            return pages
    except Exception as e:
        logger.error(f"خطا در استخراج تعداد صفحات PDF: {e}")
        return 0

# تابع برای استخراج تعداد صفحات از فایل Word
async def extract_docx_pages(file_path):
    try:
        logger.info(f"استخراج تعداد صفحات Word از فایل: {file_path}")
        doc = docx.Document(file_path)
        pages = len(doc.paragraphs) // 20 + 1  # تخمین تقریبی تعداد صفحات
        logger.info(f"تعداد صفحات Word: {pages}")
        return pages
    except Exception as e:
        logger.error(f"خطا در استخراج تعداد صفحات Word: {e}")
        return 0

# تابع برای استخراج تعداد صفحات از فایل PowerPoint
async def extract_pptx_pages(file_path):
    try:
        logger.info(f"استخراج تعداد صفحات PowerPoint از فایل: {file_path}")
        presentation = pptx.Presentation(file_path)
        slides = len(presentation.slides)
        logger.info(f"تعداد صفحات PowerPoint: {slides}")
        return slides
    except Exception as e:
        logger.error(f"خطا در استخراج تعداد صفحات PowerPoint: {e}")
        return 0

# تابع برای تشخیص نوع فایل و استخراج تعداد صفحات
async def get_file_pages(file_path):
    file_extension = os.path.splitext(file_path)[1].lower()
    
    if file_extension == '.pdf':
        return 'pdf', await extract_pdf_pages(file_path)
    elif file_extension == '.docx':
        return 'docx', await extract_docx_pages(file_path)
    elif file_extension == '.pptx':
        return 'pptx', await extract_pptx_pages(file_path)
    elif file_extension in ['.jpg', '.jpeg', '.png']:
        return 'image', 1
    else:
        return 'unknown', 0

# تابع برای محاسبه قیمت پرینت
async def calculate_print_price(print_data):
    try:
        # دریافت قیمت‌های پایه
        prices = get_print_prices()
        if not prices:
            return 0
        
        # استخراج اطلاعات سفارش
        page_count = print_data.get('page_count', 0)
        print_type = print_data.get('print_type', 'bw')  # سیاه و سفید یا رنگی
        print_method = print_data.get('print_method', 'single')  # یک رو یا دو رو
        paper_size = print_data.get('paper_size', 'a4')  # A4, A5, A3
        paper_type = print_data.get('paper_type', 'normal')  # معمولی یا گلاسه
        staple = print_data.get('staple', False)  # منگنه
        delivery_type = print_data.get('delivery_type', 'in_person')  # حضوری یا پیک
        
        # پیدا کردن قیمت مناسب بر اساس بازه صفحات
        price_per_page = 0
        for price_range in prices.get('price_ranges', []):
            if (price_range['print_type'] == print_type and 
                price_range['print_method'] == print_method and 
                price_range['paper_size'] == paper_size and 
                price_range['paper_type'] == paper_type and 
                price_range['range_start'] <= page_count <= price_range['range_end']):
                price_per_page = price_range['price_per_page']
                break
        
        # محاسبه قیمت کل بر اساس تعداد صفحات
        total_price = price_per_page * page_count
        
        # اضافه کردن هزینه منگنه در صورت نیاز
        if staple:
            total_price += prices.get('staple_price', 0)
        
        # اضافه کردن هزینه پیک در صورت نیاز
        if delivery_type == 'delivery' and prices.get('delivery_enabled', False):
            total_price += prices.get('delivery_price', 0)
        
        return total_price
    except Exception as e:
        logger.error(f"خطا در محاسبه قیمت پرینت: {e}")
        return 0

# تابع برای نمایش تأیید نهایی سفارش
async def show_order_confirmation(update, context, user_id):
    try:
        # دریافت اطلاعات سفارش
        print_data = user_print_data.get(user_id, {})
        if not print_data:
            raise ValueError("اطلاعات سفارش یافت نشد")
        
        # محاسبه قیمت کل
        total_price = await calculate_print_price(print_data)
        print_data["total_price"] = total_price
        
        # ساخت متن تأیید سفارش
        confirmation_text = "📋 خلاصه سفارش شما:\n\n"
        
        # اطلاعات فایل
        if print_data.get("file_type") == "image":
            confirmation_text += f"📷 نوع فایل: تصویر\n"
            confirmation_text += f"📊 تعداد تصاویر: {print_data.get('images_count', 0)}\n"
        else:
            confirmation_text += f"📄 نوع فایل: {print_data.get('file_type', '').upper()}\n"
            confirmation_text += f"📊 تعداد صفحات: {print_data.get('page_count', 0)}\n"
            if print_data.get("page_range") and print_data.get("page_range") != "all":
                confirmation_text += f"🔢 محدوده صفحات: {print_data.get('page_range')}\n"
        
        # اطلاعات چاپ
        print_type_text = "رنگی" if print_data.get("print_type") == "color" else "سیاه و سفید"
        confirmation_text += f"🖨️ نوع چاپ: {print_type_text}\n"
        
        print_method_text = "دو رو" if print_data.get("print_method") == "double" else "یک رو"
        confirmation_text += f"📑 روش چاپ: {print_method_text}\n"
        
        paper_size_text = print_data.get("paper_size", "a4").upper()
        confirmation_text += f"📏 اندازه کاغذ: {paper_size_text}\n"
        
        paper_type_map = {
            "normal": "معمولی",
            "glossy_175": "گلاسه 175 گرمی",
            "glossy_250": "گلاسه 250 گرمی"
        }
        paper_type_text = paper_type_map.get(print_data.get("paper_type", "normal"), "معمولی")
        confirmation_text += f"📃 نوع کاغذ: {paper_type_text}\n"
        
        if print_data.get("staple"):
            confirmation_text += "📎 منگنه: بله\n"
        
        # اطلاعات تحویل
        delivery_type_text = "ارسال با پیک" if print_data.get("delivery_type") == "delivery" else "تحویل حضوری"
        confirmation_text += f"🚚 نوع تحویل: {delivery_type_text}\n"
        
        if print_data.get("delivery_type") == "delivery" and print_data.get("address"):
            confirmation_text += f"📍 آدرس: {print_data.get('address')}\n"
        
        # اطلاعات تماس
        confirmation_text += f"👤 نام و نام خانوادگی: {print_data.get('full_name', '')}\n"
        confirmation_text += f"📱 شماره تماس: {print_data.get('phone_number', '')}\n"
        
        # توضیحات
        if print_data.get("description"):
            confirmation_text += f"\n📝 توضیحات: {print_data.get('description')}\n"
        
        # قیمت کل
        formatted_price = format_number_with_commas(total_price)
        confirmation_text += f"\n💰 قیمت کل: {formatted_price} تومان"
        
        # دریافت موجودی کاربر
        user_profile = get_user_profile(user_id)
        user_balance = user_profile.get("balance", 0)
        formatted_balance = format_number_with_commas(user_balance)
        
        # اضافه کردن اطلاعات موجودی
        confirmation_text += f"\n💳 موجودی شما: {formatted_balance} تومان"
        
        # بررسی کافی بودن موجودی
        if user_balance >= total_price:
            confirmation_text += "\n\n✅ موجودی شما برای این سفارش کافی است."
            
            # دکمه‌های تأیید و لغو
            keyboard = [
                [InlineKeyboardButton("✅ تأیید و پرداخت", callback_data="confirm_order^balance")],
                [InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]
            ]
        else:
            # محاسبه مبلغ کسری
            shortage = total_price - user_balance
            formatted_shortage = format_number_with_commas(shortage)
            
            confirmation_text += f"\n\n❌ موجودی شما برای این سفارش کافی نیست. شما به {formatted_shortage} تومان دیگر نیاز دارید."
            
            # دکمه‌های افزایش موجودی یا پرداخت با موجودی فعلی
            keyboard = []
            
            if user_balance > 0:
                keyboard.append([InlineKeyboardButton("💰 پرداخت با موجودی فعلی + واریز مابقی", callback_data="confirm_order^partial")])
            
            keyboard.append([InlineKeyboardButton("💳 افزایش موجودی", callback_data="confirm_order^increase")])
            keyboard.append([InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")])
        
        # ارسال پیام تأیید
        if isinstance(update, Update):
            if update.message:
                await update.message.reply_text(confirmation_text, reply_markup=InlineKeyboardMarkup(keyboard))
            elif update.callback_query:
                await update.callback_query.edit_message_text(confirmation_text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            # اگر update یک شیء Update نباشد، از context برای ارسال پیام استفاده می‌کنیم
            await context.bot.send_message(chat_id=user_id, text=confirmation_text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        logger.error(f"خطا در نمایش تأیید سفارش: {e}")
        
        # ارسال پیام خطا
        error_message = "❌ خطایی در پردازش سفارش رخ داد. لطفاً مجدداً تلاش کنید."
        
        if isinstance(update, Update):
            if update.message:
                await update.message.reply_text(error_message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]]))
            elif update.callback_query:
                await update.callback_query.edit_message_text(error_message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]]))
        else:
            await context.bot.send_message(chat_id=user_id, text=error_message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="serviceslist^")]]))

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
    application.add_handler(MessageHandler(filters.Document.ALL, handle_message))  # اضافه کردن هندلر برای فایل‌های document
    
    # شروع پولینگ
    logger.info(f"ربات {BOT_CONFIG['bot-name']} شروع به کار کرد...")
    application.run_polling()

if __name__ == "__main__":
    main() 