import sqlite3
import logging
import os
from datetime import datetime
from config import DB_CONFIG

# تنظیم لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# مسیر پایگاه داده
DB_PATH = DB_CONFIG["db_path"]

# تابع برای ایجاد پایگاه داده
def setup_database():
    try:
        # بررسی وجود فایل دیتابیس
        db_exists = os.path.isfile(DB_PATH)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # ایجاد جدول کاربران اگر وجود نداشته باشد
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            phone_number TEXT DEFAULT '',
            balance INTEGER DEFAULT 0,
            username TEXT DEFAULT '',
            created_at INTEGER
        )
        ''')
        
        # ایجاد جدول معرفی‌ها اگر وجود نداشته باشد
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_user_id INTEGER,
            invitee_user_id INTEGER,
            inviter_cart_amount INTEGER,
            invitee_cart_amount INTEGER,
            referral_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (inviter_user_id) REFERENCES users (user_id),
            FOREIGN KEY (invitee_user_id) REFERENCES users (user_id)
        )
        ''')
        
        conn.commit()
        conn.close()
        
        if db_exists:
            logger.info("اتصال به پایگاه داده موجود با موفقیت انجام شد")
        else:
            logger.info("پایگاه داده جدید با موفقیت ایجاد شد")
        return True
    except Exception as e:
        logger.error(f"خطا در ایجاد/اتصال به پایگاه داده: {e}")
        return False

# تابع برای بررسی وجود کاربر
def check_user_exists(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()[0] > 0
        conn.close()
        return result
    except Exception as e:
        logger.error(f"خطا در بررسی وجود کاربر: {e}")
        return False

# تابع برای ثبت کاربر جدید
def register_user(user_id, username, created_at=None):
    try:
        if created_at is None:
            created_at = int(datetime.now().timestamp())
            
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, phone_number, balance, username, created_at) VALUES (?, '', 0, ?, ?)",
            (user_id, username or "", created_at)
        )
        conn.commit()
        conn.close()
        logger.info(f"کاربر جدید با شناسه {user_id} ثبت شد")
        return True
    except Exception as e:
        logger.error(f"خطا در ثبت کاربر جدید: {e}")
        return False

# تابع برای دریافت اطلاعات کاربر
def get_user_profile(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # دریافت موجودی کاربر
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance_result = cursor.fetchone()
        balance = balance_result[0] if balance_result else 0
        
        # دریافت تعداد معرفی‌ها
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE inviter_user_id = ?", (user_id,))
        referral_count = cursor.fetchone()[0]
        
        # دریافت مجموع مبلغ معرفی‌ها
        cursor.execute("SELECT COALESCE(SUM(inviter_cart_amount), 0) FROM referrals WHERE inviter_user_id = ?", (user_id,))
        total_inviter_cart = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "balance": balance,
            "referralCount": referral_count,
            "totalInviterCart": total_inviter_cart or 0
        }
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات کاربر: {e}")
        return {
            "balance": 0,
            "referralCount": 0,
            "totalInviterCart": 0
        }

# تابع برای ثبت معرفی جدید و به‌روزرسانی موجودی
def register_referral(inviter_id, invitee_id, amount):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # بررسی تکراری نبودن معرفی
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE inviter_user_id = ? AND invitee_user_id = ?", 
                      (inviter_id, invitee_id))
        exists = cursor.fetchone()[0] > 0
        
        if exists:
            logger.warning(f"معرفی تکراری: دعوت‌کننده {inviter_id}، دعوت‌شونده {invitee_id}")
            conn.close()
            return False
            
        # افزایش موجودی دعوت‌کننده
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, inviter_id))
        
        # افزایش موجودی دعوت‌شونده
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, invitee_id))
        
        # ثبت اطلاعات معرفی
        cursor.execute(
            "INSERT INTO referrals (inviter_user_id, invitee_user_id, inviter_cart_amount, invitee_cart_amount, referral_date) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (inviter_id, invitee_id, amount, amount)
        )
        
        conn.commit()
        conn.close()
        logger.info(f"معرفی جدید ثبت شد: دعوت‌کننده {inviter_id}، دعوت‌شونده {invitee_id}")
        return True
    except Exception as e:
        logger.error(f"خطا در ثبت معرفی جدید: {e}")
        return False

# تابع برای به‌روزرسانی موجودی کاربر
def update_user_balance(user_id, amount):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        logger.info(f"موجودی کاربر {user_id} به مقدار {amount} به‌روزرسانی شد")
        return True
    except Exception as e:
        logger.error(f"خطا در به‌روزرسانی موجودی کاربر: {e}")
        return False

# تابع برای ثبت شماره تلفن کاربر
def update_user_phone(user_id, phone_number):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET phone_number = ? WHERE user_id = ?", (phone_number, user_id))
        conn.commit()
        conn.close()
        logger.info(f"شماره تلفن کاربر {user_id} به‌روزرسانی شد")
        return True
    except Exception as e:
        logger.error(f"خطا در به‌روزرسانی شماره تلفن کاربر: {e}")
        return False

# تابع برای دریافت لیست تمام کاربران
def get_all_users():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, balance, created_at FROM users ORDER BY created_at DESC")
        users = cursor.fetchall()
        conn.close()
        
        return users
    except Exception as e:
        logger.error(f"خطا در دریافت لیست کاربران: {e}")
        return [] 