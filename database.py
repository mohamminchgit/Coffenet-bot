import sqlite3
import logging
import os
from datetime import datetime
from config import DB_CONFIG
import time

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
        
        # ایجاد جدول تراکنش‌ها اگر وجود نداشته باشد
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            file_id TEXT,
            message_id INTEGER,
            status TEXT DEFAULT 'pending',
            admin_note TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        # ایجاد جدول اطلاعات کارت اگر وجود نداشته باشد
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_info (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            card_number TEXT,
            card_holder TEXT
        )
        ''')
        
        # ایجاد جدول تنظیمات قیمت پرینت
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS print_prices (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            bw_single_a4 INTEGER DEFAULT 500,
            bw_double_a4 INTEGER DEFAULT 800,
            color_single_a4 INTEGER DEFAULT 1500,
            color_double_a4 INTEGER DEFAULT 2500,
            bw_single_a5 INTEGER DEFAULT 300,
            bw_double_a5 INTEGER DEFAULT 500,
            color_single_a5 INTEGER DEFAULT 1000,
            color_double_a5 INTEGER DEFAULT 1800,
            bw_single_a3 INTEGER DEFAULT 1000,
            bw_double_a3 INTEGER DEFAULT 1800,
            color_single_a3 INTEGER DEFAULT 3000,
            color_double_a3 INTEGER DEFAULT 5000,
            glossy_175_a4 INTEGER DEFAULT 3000,
            glossy_250_a4 INTEGER DEFAULT 4000,
            glossy_175_a3 INTEGER DEFAULT 6000,
            glossy_250_a3 INTEGER DEFAULT 8000,
            staple_price INTEGER DEFAULT 500,
            delivery_price INTEGER DEFAULT 50000,
            delivery_enabled BOOLEAN DEFAULT 1
        )
        ''')
        
        # ایجاد جدول قیمت‌های بازه‌ای پرینت
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS print_price_ranges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            print_type TEXT NOT NULL,
            print_method TEXT NOT NULL,
            paper_size TEXT NOT NULL,
            paper_type TEXT NOT NULL,
            range_start INTEGER NOT NULL,
            range_end INTEGER NOT NULL,
            price_per_page INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # ایجاد جدول سفارشات پرینت
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS print_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_ids TEXT,
            file_type TEXT,
            page_count INTEGER,
            page_range TEXT,
            print_type TEXT,
            print_method TEXT,
            paper_size TEXT,
            paper_type TEXT,
            staple BOOLEAN,
            delivery_type TEXT,
            full_name TEXT,
            phone_number TEXT,
            address TEXT,
            description TEXT,
            total_price INTEGER,
            final_price INTEGER DEFAULT NULL,
            offer_id INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        # ایجاد جدول آدرس‌های کاربران
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        # بررسی و درج مقادیر پیش‌فرض برای قیمت‌های پرینت
        cursor.execute("SELECT COUNT(*) FROM print_prices")
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
            INSERT INTO print_prices (id) VALUES (1)
            ''')
        
        # بررسی و درج مقادیر پیش‌فرض برای قیمت‌های بازه‌ای پرینت
        cursor.execute("SELECT COUNT(*) FROM print_price_ranges")
        if cursor.fetchone()[0] == 0:
            # چاپ سیاه‌وسفید - A4 - رو تک
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('bw', 'single', 'a4', 'normal', 1, 20, 4500),
                   ('bw', 'single', 'a4', 'normal', 21, 50, 4000),
                   ('bw', 'single', 'a4', 'normal', 51, 9999, 3500)
            ''')
            
            # چاپ سیاه‌وسفید - A4 - رو دو
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('bw', 'double', 'a4', 'normal', 1, 20, 5000),
                   ('bw', 'double', 'a4', 'normal', 21, 50, 4500),
                   ('bw', 'double', 'a4', 'normal', 51, 9999, 4000)
            ''')
            
            # چاپ سیاه‌وسفید - A5 - رو تک
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('bw', 'single', 'a5', 'normal', 1, 20, 2500),
                   ('bw', 'single', 'a5', 'normal', 21, 50, 2200),
                   ('bw', 'single', 'a5', 'normal', 51, 9999, 2000)
            ''')
            
            # چاپ سیاه‌وسفید - A5 - رو دو
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('bw', 'double', 'a5', 'normal', 1, 20, 3000),
                   ('bw', 'double', 'a5', 'normal', 21, 50, 2700),
                   ('bw', 'double', 'a5', 'normal', 51, 9999, 2500)
            ''')
            
            # چاپ سیاه‌وسفید - A3 - رو تک
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('bw', 'single', 'a3', 'normal', 1, 20, 8000),
                   ('bw', 'single', 'a3', 'normal', 21, 50, 7500),
                   ('bw', 'single', 'a3', 'normal', 51, 9999, 7000)
            ''')
            
            # چاپ رنگی - A4 - رو تک
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('color', 'single', 'a4', 'normal', 1, 20, 10000),
                   ('color', 'single', 'a4', 'normal', 21, 50, 9000),
                   ('color', 'single', 'a4', 'normal', 51, 9999, 8000)
            ''')
            
            # چاپ رنگی - A4 - رو دو
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('color', 'double', 'a4', 'normal', 1, 20, 15000),
                   ('color', 'double', 'a4', 'normal', 21, 50, 14000),
                   ('color', 'double', 'a4', 'normal', 51, 9999, 13000)
            ''')
            
            # چاپ رنگی - A5 - رو تک
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('color', 'single', 'a5', 'normal', 1, 20, 6000),
                   ('color', 'single', 'a5', 'normal', 21, 50, 5500),
                   ('color', 'single', 'a5', 'normal', 51, 9999, 5000)
            ''')
            
            # چاپ رنگی - A5 - رو دو
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('color', 'double', 'a5', 'normal', 1, 20, 8000),
                   ('color', 'double', 'a5', 'normal', 21, 50, 7500),
                   ('color', 'double', 'a5', 'normal', 51, 9999, 7000)
            ''')
            
            # چاپ رنگی - A3 - رو تک
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('color', 'single', 'a3', 'normal', 1, 20, 20000),
                   ('color', 'single', 'a3', 'normal', 21, 50, 18000),
                   ('color', 'single', 'a3', 'normal', 51, 9999, 17000)
            ''')
            
            # چاپ رنگی روی کاغذ گلاسه 175 گرمی
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('color', 'single', 'a4', 'glossy_175', 1, 9999, 25000),
                   ('color', 'single', 'a3', 'glossy_175', 1, 9999, 45000)
            ''')
            
            # چاپ رنگی روی کاغذ گلاسه 250 گرمی
            cursor.execute('''
            INSERT INTO print_price_ranges (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
            VALUES ('color', 'single', 'a4', 'glossy_250', 1, 9999, 30000)
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

# تابع برای ثبت تراکنش جدید
def register_transaction(user_id, amount, file_id, message_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # ثبت تراکنش جدید
        cursor.execute(
            "INSERT INTO transactions (user_id, amount, file_id, message_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (user_id, amount, file_id, message_id)
        )
        
        transaction_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"تراکنش جدید با شناسه {transaction_id} برای کاربر {user_id} ثبت شد")
        return transaction_id
    except Exception as e:
        logger.error(f"خطا در ثبت تراکنش جدید: {e}")
        return None

# تابع برای به‌روزرسانی وضعیت تراکنش
def update_transaction_status(message_id, status, admin_note=''):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # به‌روزرسانی وضعیت تراکنش
        cursor.execute(
            "UPDATE transactions SET status = ?, admin_note = ?, updated_at = CURRENT_TIMESTAMP WHERE message_id = ?",
            (status, admin_note, message_id)
        )
        
        # بررسی آیا تراکنشی به‌روزرسانی شد
        if cursor.rowcount == 0:
            logger.warning(f"هیچ تراکنشی با شناسه پیام {message_id} یافت نشد")
            conn.close()
            return False
        
        conn.commit()
        conn.close()
        
        logger.info(f"وضعیت تراکنش با شناسه پیام {message_id} به {status} تغییر یافت")
        return True
    except Exception as e:
        logger.error(f"خطا در به‌روزرسانی وضعیت تراکنش: {e}")
        return False

# تابع برای دریافت اطلاعات تراکنش با شناسه پیام
def get_transaction_by_message_id(message_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, user_id, amount, file_id, status, admin_note, created_at FROM transactions WHERE message_id = ?",
            (message_id,)
        )
        
        transaction = cursor.fetchone()
        conn.close()
        
        if transaction:
            return {
                "id": transaction[0],
                "user_id": transaction[1],
                "amount": transaction[2],
                "file_id": transaction[3],
                "status": transaction[4],
                "admin_note": transaction[5],
                "created_at": transaction[6]
            }
        else:
            logger.warning(f"هیچ تراکنشی با شناسه پیام {message_id} یافت نشد")
            return None
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات تراکنش: {e}")
        return None

# تابع برای دریافت تاریخچه تراکنش‌های کاربر
def get_user_transactions(user_id, limit=10):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, amount, status, created_at, updated_at FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        
        transactions = cursor.fetchall()
        conn.close()
        
        result = []
        for transaction in transactions:
            result.append({
                "id": transaction[0],
                "amount": transaction[1],
                "status": transaction[2],
                "created_at": transaction[3],
                "updated_at": transaction[4]
            })
        
        return result
    except Exception as e:
        logger.error(f"خطا در دریافت تاریخچه تراکنش‌های کاربر: {e}")
        return []

def get_card_info():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT card_number, card_holder FROM card_info WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"card_number": row[0], "card_holder": row[1]}
        return None
    except Exception as e:
        logger.error(f"خطا در دریافت اطلاعات کارت: {e}")
        return None

def set_card_info(card_number, card_holder):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO card_info (id, card_number, card_holder) VALUES (1, ?, ?)", (card_number, card_holder))
        conn.commit()
        conn.close()
        logger.info("اطلاعات کارت با موفقیت ذخیره شد")
        return True
    except Exception as e:
        logger.error(f"خطا در ذخیره اطلاعات کارت: {e}")
        return False

def get_stats():
    now = int(time.time())
    today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    yesterday_start = today_start - 86400
    week_start = today_start - 7*86400
    last_week_start = week_start - 7*86400
    month_start = today_start - 30*86400
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # کل کاربران
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # کاربران امروز
        cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (today_start,))
        today_users = cursor.fetchone()[0]
        
        # کاربران دیروز
        cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= ? AND created_at < ?", (yesterday_start, today_start))
        yesterday_users = cursor.fetchone()[0]
        
        # کاربران هفته جاری
        cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (week_start,))
        week_users = cursor.fetchone()[0]
        
        # کاربران هفته گذشته
        cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= ? AND created_at < ?", (last_week_start, week_start))
        last_week_users = cursor.fetchone()[0]
        
        # کاربران ماه گذشته
        cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= ?", (month_start,))
        month_users = cursor.fetchone()[0]
        
        # کاربران دعوت شده (کل)
        cursor.execute("SELECT COUNT(*) FROM referrals")
        total_referrals = cursor.fetchone()[0]
        
        # کاربران دعوت شده امروز
        cursor.execute("""
            SELECT COUNT(*) FROM referrals 
            WHERE referral_date >= datetime(?, 'unixepoch')
        """, (today_start,))
        today_referrals = cursor.fetchone()[0]
        
        # کاربران دعوت شده دیروز
        cursor.execute("""
            SELECT COUNT(*) FROM referrals 
            WHERE referral_date >= datetime(?, 'unixepoch') 
            AND referral_date < datetime(?, 'unixepoch')
        """, (yesterday_start, today_start))
        yesterday_referrals = cursor.fetchone()[0]
        
        # کاربران دعوت شده هفته جاری
        cursor.execute("""
            SELECT COUNT(*) FROM referrals 
            WHERE referral_date >= datetime(?, 'unixepoch')
        """, (week_start,))
        week_referrals = cursor.fetchone()[0]
        
        # کاربران فعال امروز (کسانی که تراکنش یا پیام داشته‌اند)
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM transactions WHERE created_at >= ?", (today_start,))
        active_today = cursor.fetchone()[0]
        
        # کاربران فعال دیروز
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM transactions WHERE created_at >= ? AND created_at < ?", (yesterday_start, today_start))
        active_yesterday = cursor.fetchone()[0]
        
        # کاربران فعال هفته جاری
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM transactions WHERE created_at >= ?", (week_start,))
        active_week = cursor.fetchone()[0]
        
        # مجموع موجودی کاربران
        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0
        
        conn.close()
        return {
            "total_users": total_users,
            "today_users": today_users,
            "yesterday_users": yesterday_users,
            "week_users": week_users,
            "last_week_users": last_week_users,
            "month_users": month_users,
            "total_referrals": total_referrals,
            "today_referrals": today_referrals,
            "yesterday_referrals": yesterday_referrals,
            "week_referrals": week_referrals,
            "active_today": active_today,
            "active_yesterday": active_yesterday,
            "active_week": active_week,
            "total_balance": total_balance
        }
    except Exception as e:
        logger.error(f"خطا در دریافت آمار: {e}")
        return None

def get_top_inviters(limit=10):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT inviter_user_id, COUNT(*) as invites
            FROM referrals
            GROUP BY inviter_user_id
            ORDER BY invites DESC
            LIMIT ?
        ''', (limit,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"خطا در دریافت برترین دعوت‌کنندگان: {e}")
        return []

def get_loyal_users(min_weeks=2):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # هر کاربری که در حداقل min_weeks مختلف تراکنش داشته باشد
        cursor.execute('''
            SELECT user_id, COUNT(DISTINCT strftime('%Y-%W', datetime(created_at, 'unixepoch')))
            FROM transactions
            GROUP BY user_id
            HAVING COUNT(DISTINCT strftime('%Y-%W', datetime(created_at, 'unixepoch'))) >= ?
            ORDER BY COUNT(DISTINCT strftime('%Y-%W', datetime(created_at, 'unixepoch'))) DESC
        ''', (min_weeks,))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error(f"خطا در دریافت کاربران وفادار: {e}")
        return []

def get_growth_chart(days=14):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT date(datetime(created_at, 'unixepoch')), COUNT(*)
            FROM users
            WHERE created_at >= strftime('%s', date('now', ? || ' days'))
            GROUP BY date(datetime(created_at, 'unixepoch'))
            ORDER BY date(datetime(created_at, 'unixepoch')) DESC
            LIMIT ?
        ''', (-days, days))
        rows = cursor.fetchall()
        conn.close()
        return rows[::-1]  # برعکس برای نمایش از قدیم به جدید
    except Exception as e:
        logger.error(f"خطا در دریافت نمودار رشد: {e}")
        return []

def get_usernames(user_ids):
    if not user_ids:
        return {}
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        q = f"SELECT user_id, username FROM users WHERE user_id IN ({','.join(['?']*len(user_ids))})"
        cursor.execute(q, user_ids)
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}
    except Exception as e:
        logger.error(f"خطا در دریافت نام کاربری: {e}")
        return {}

def get_referrals_by_inviter(inviter_user_id):
    """
    دریافت لیست کاربران دعوت‌شده توسط یک دعوت‌کننده خاص
    خروجی: لیستی از دیکشنری شامل invitee_user_id، username، created_at، referral_date، inviter_cart_amount، invitee_cart_amount
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.username, u.created_at, r.referral_date, r.inviter_cart_amount, r.invitee_cart_amount
            FROM referrals r
            JOIN users u ON r.invitee_user_id = u.user_id
            WHERE r.inviter_user_id = ?
            ORDER BY r.referral_date DESC
        ''', (inviter_user_id,))
        rows = cursor.fetchall()
        conn.close()
        result = []
        for row in rows:
            result.append({
                'invitee_user_id': row[0],
                'username': row[1],
                'created_at': row[2],
                'referral_date': row[3],
                'inviter_cart_amount': row[4],
                'invitee_cart_amount': row[5],
            })
        return result
    except Exception as e:
        logger.error(f"خطا در دریافت لیست دعوت‌شدگان: {e}")
        return []

def get_top_inviter_by_amount():
    """
    کاربری که بیشترین مبلغ پاداش دعوت را دریافت کرده است (بر اساس inviter_cart_amount)
    خروجی: (user_id, username, total_amount)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.username, SUM(r.inviter_cart_amount) as total_amount
            FROM referrals r
            JOIN users u ON r.inviter_user_id = u.user_id
            GROUP BY r.inviter_user_id
            ORDER BY total_amount DESC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0], row[1], row[2]
        return None
    except Exception as e:
        logger.error(f"خطا در دریافت بیشترین مبلغ دعوت: {e}")
        return None

def get_top_inviter_by_count():
    """
    کاربری که بیشترین تعداد دعوت موفق داشته است
    خروجی: (user_id, username, count)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT u.user_id, u.username, COUNT(r.id) as invite_count
            FROM referrals r
            JOIN users u ON r.inviter_user_id = u.user_id
            GROUP BY r.inviter_user_id
            ORDER BY invite_count DESC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0], row[1], row[2]
        return None
    except Exception as e:
        logger.error(f"خطا در دریافت بیشترین تعداد دعوت: {e}")
        return None

def get_total_referral_rewards():
    """
    مجموع کل پاداش پرداختی به دعوت‌کنندگان و دعوت‌شونده‌ها
    خروجی: (total_inviter, total_invitee)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(inviter_cart_amount), SUM(invitee_cart_amount) FROM referrals')
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0] or 0, row[1] or 0
        return 0, 0
    except Exception as e:
        logger.error(f"خطا در دریافت مجموع پاداش دعوت: {e}")
        return 0, 0

# تابع برای دریافت قیمت‌های پرینت
def get_print_prices():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # دریافت قیمت‌های بازه‌ای
        cursor.execute("SELECT * FROM print_price_ranges")
        price_ranges = cursor.fetchall()
        
        # دریافت قیمت‌های ثابت (منگنه و پیک)
        cursor.execute("SELECT staple_price, delivery_price, delivery_enabled FROM print_prices WHERE id = 1")
        fixed_prices = cursor.fetchone()
        
        conn.close()
        
        if not price_ranges or not fixed_prices:
            return None
        
        # ساخت دیکشنری قیمت‌ها
        prices = {
            "price_ranges": [],
            "staple_price": fixed_prices[0],
            "delivery_price": fixed_prices[1],
            "delivery_enabled": fixed_prices[2]
        }
        
        # افزودن قیمت‌های بازه‌ای
        for price_range in price_ranges:
            prices["price_ranges"].append({
                "print_type": price_range[1],
                "print_method": price_range[2],
                "paper_size": price_range[3],
                "paper_type": price_range[4],
                "range_start": price_range[5],
                "range_end": price_range[6],
                "price_per_page": price_range[7]
            })
        
        return prices
    except Exception as e:
        logger.error(f"خطا در دریافت قیمت‌های پرینت: {e}")
        return None

# تابع برای به‌روزرسانی قیمت‌های پرینت
def update_print_prices(prices):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # به‌روزرسانی قیمت‌های ثابت
        if "staple_price" in prices or "delivery_price" in prices or "delivery_enabled" in prices:
            query = "UPDATE print_prices SET "
            params = []
            
            if "staple_price" in prices:
                query += "staple_price = ?, "
                params.append(prices["staple_price"])
            
            if "delivery_price" in prices:
                query += "delivery_price = ?, "
                params.append(prices["delivery_price"])
            
            if "delivery_enabled" in prices:
                query += "delivery_enabled = ?, "
                params.append(prices["delivery_enabled"])
            
            # حذف کاما و فاصله اضافی از انتهای کوئری
            query = query[:-2]
            query += " WHERE id = 1"
            
            cursor.execute(query, params)
        
        # به‌روزرسانی قیمت‌های بازه‌ای
        if "price_ranges" in prices:
            # حذف تمام قیمت‌های بازه‌ای موجود
            cursor.execute("DELETE FROM print_price_ranges")
            
            # افزودن قیمت‌های بازه‌ای جدید
            for price_range in prices["price_ranges"]:
                cursor.execute('''
                INSERT INTO print_price_ranges 
                (print_type, print_method, paper_size, paper_type, range_start, range_end, price_per_page)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    price_range["print_type"],
                    price_range["print_method"],
                    price_range["paper_size"],
                    price_range["paper_type"],
                    price_range["range_start"],
                    price_range["range_end"],
                    price_range["price_per_page"]
                ))
        
        conn.commit()
        conn.close()
        logger.info("قیمت‌های پرینت با موفقیت به‌روزرسانی شد")
        return True
    except Exception as e:
        logger.error(f"خطا در به‌روزرسانی قیمت‌های پرینت: {e}")
        return False

# تابع برای ذخیره آدرس جدید کاربر
def save_user_address(user_id, address):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO user_addresses (user_id, address) VALUES (?, ?)",
            (user_id, address)
        )
        
        address_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"آدرس جدید برای کاربر {user_id} ذخیره شد")
        return address_id
    except Exception as e:
        logger.error(f"خطا در ذخیره آدرس کاربر: {e}")
        return None

# تابع برای دریافت آدرس‌های کاربر
def get_user_addresses(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, address FROM user_addresses WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        
        addresses = cursor.fetchall()
        conn.close()
        
        result = []
        for address in addresses:
            result.append({
                "id": address[0],
                "address": address[1]
            })
        
        return result
    except Exception as e:
        logger.error(f"خطا در دریافت آدرس‌های کاربر: {e}")
        return []

# تابع برای ثبت سفارش پرینت
def register_print_order(user_id, file_ids, file_type, page_count, page_range, print_type, print_method,
                        paper_size, paper_type, staple, delivery_type, full_name, phone_number, address,
                        description, total_price, final_price=None, offer_id=None):
    """
    ثبت سفارش پرینت در پایگاه داده
    
    Args:
        user_id: شناسه کاربر
        file_ids: شناسه فایل‌ها با کاما جدا شده
        file_type: نوع فایل (pdf, docx, image, ...)
        page_count: تعداد صفحات
        page_range: محدوده صفحات
        print_type: نوع چاپ (رنگی یا سیاه و سفید)
        print_method: روش چاپ (یک رو یا دو رو)
        paper_size: اندازه کاغذ
        paper_type: نوع کاغذ
        staple: منگنه (0 یا 1)
        delivery_type: نوع تحویل (حضوری یا پیک)
        full_name: نام و نام خانوادگی
        phone_number: شماره تماس
        address: آدرس (برای تحویل با پیک)
        description: توضیحات
        total_price: قیمت کل قبل از تخفیف
        final_price: قیمت نهایی پس از تخفیف
        offer_id: شناسه پیشنهاد ویژه استفاده شده
        
    Returns:
        int: شناسه سفارش یا None در صورت خطا
    """
    try:
        now = int(datetime.now().timestamp())
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # اضافه کردن ستون‌های جدید به جدول print_orders در صورت نیاز
        try:
            cursor.execute("SELECT final_price FROM print_orders LIMIT 1")
        except sqlite3.OperationalError:
            # ستون‌های مورد نیاز وجود ندارند، آنها را اضافه می‌کنیم
            cursor.execute("ALTER TABLE print_orders ADD COLUMN final_price INTEGER DEFAULT NULL")
            cursor.execute("ALTER TABLE print_orders ADD COLUMN offer_id INTEGER DEFAULT NULL")
            conn.commit()
        
        cursor.execute('''
            INSERT INTO print_orders (
                user_id, file_ids, file_type, page_count, page_range, print_type, print_method,
                paper_size, paper_type, staple, delivery_type, full_name, phone_number, 
                address, description, total_price, final_price, offer_id, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, file_ids, file_type, page_count, page_range, print_type, print_method,
            paper_size, paper_type, staple, delivery_type, full_name, phone_number, 
            address, description, total_price, final_price or total_price, offer_id, 'pending', now
        ))
        
        order_id = cursor.lastrowid
        
        # به‌روزرسانی اطلاعات کاربر
        if full_name and phone_number:
            cursor.execute('''
                UPDATE users 
                SET phone_number = ? 
                WHERE user_id = ? AND (phone_number IS NULL OR phone_number = '')
            ''', (phone_number, user_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"سفارش پرینت جدید با شناسه {order_id} ثبت شد")
        return order_id
    except Exception as e:
        logger.error(f"خطا در ثبت سفارش پرینت: {e}")
        return None

# تابع برای به‌روزرسانی وضعیت سفارش پرینت
def update_print_order_status(order_id, status):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE print_orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, order_id)
        )
        
        # بررسی آیا سفارشی به‌روزرسانی شد
        if cursor.rowcount == 0:
            logger.warning(f"هیچ سفارشی با شناسه {order_id} یافت نشد")
            conn.close()
            return False
        
        conn.commit()
        conn.close()
        
        logger.info(f"وضعیت سفارش پرینت با شناسه {order_id} به {status} تغییر یافت")
        return True
    except Exception as e:
        logger.error(f"خطا در به‌روزرسانی وضعیت سفارش پرینت: {e}")
        return False

# تابع برای دریافت سفارش‌های پرینت کاربر
def get_user_print_orders(user_id, limit=10):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, file_type, page_count, total_price, status, created_at FROM print_orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        
        orders = cursor.fetchall()
        conn.close()
        
        result = []
        for order in orders:
            result.append({
                "id": order[0],
                "file_type": order[1],
                "page_count": order[2],
                "total_price": order[3],
                "status": order[4],
                "created_at": order[5]
            })
        
        return result
    except Exception as e:
        logger.error(f"خطا در دریافت سفارش‌های پرینت کاربر: {e}")
        return []

# تابع برای دریافت جزئیات سفارش پرینت
def get_print_order_details(order_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM print_orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        conn.close()
        
        if order:
            column_names = [description[0] for description in cursor.description]
            order_details = {}
            for i, name in enumerate(column_names):
                order_details[name] = order[i]
            return order_details
        return None
    except Exception as e:
        logger.error(f"خطا در دریافت جزئیات سفارش پرینت: {e}")
        return None

# تابع برای دریافت تمام سفارش‌های پرینت
def get_all_print_orders(limit=20, status=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if status:
            cursor.execute(
                "SELECT * FROM print_orders WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM print_orders ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        
        orders = cursor.fetchall()
        conn.close()
        
        result = []
        if orders:
            column_names = [description[0] for description in cursor.description]
            for order in orders:
                order_details = {}
                for i, name in enumerate(column_names):
                    order_details[name] = order[i]
                result.append(order_details)
        
        return result
    except Exception as e:
        logger.error(f"خطا در دریافت تمام سفارش‌های پرینت: {e}")
        return []

# تابع برای بررسی وجود اطلاعات کاربر (نام و شماره تلفن)
def check_user_info_exists(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # بررسی وجود سفارش قبلی با اطلاعات کاربر
        cursor.execute(
            "SELECT full_name, phone_number FROM print_orders WHERE user_id = ? AND full_name != '' AND phone_number != '' ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        
        user_info = cursor.fetchone()
        conn.close()
        
        if user_info and user_info[0] and user_info[1]:
            return {
                "full_name": user_info[0],
                "phone_number": user_info[1]
            }
        return None
    except Exception as e:
        logger.error(f"خطا در بررسی وجود اطلاعات کاربر: {e}")
        return None

# --- مدیریت پیشنهادات ویژه ---

def add_special_offer(title, description, offer_type='general', discount_amount=0, discount_percent=0, 
                     min_purchase_amount=0, required_invites=0, usage_limit=1, is_public=1, is_active=1, expires_at=None):
    """
    افزودن پیشنهاد ویژه جدید
    
    Args:
        title (str): عنوان پیشنهاد
        description (str): توضیحات پیشنهاد
        offer_type (str): نوع پیشنهاد (general, invite_based, purchase_based)
        discount_amount (int): مبلغ تخفیف (به تومان)
        discount_percent (int): درصد تخفیف (0-100)
        min_purchase_amount (int): حداقل مبلغ خرید برای فعال‌سازی (به تومان)
        required_invites (int): تعداد دعوت لازم برای فعال‌سازی
        usage_limit (int): تعداد دفعات مجاز استفاده
        is_public (int): آیا برای همه کاربران قابل مشاهده است
        is_active (int): وضعیت فعال بودن
        expires_at (int): تاریخ انقضا (timestamp)
        
    Returns:
        int: شناسه پیشنهاد ویژه یا None در صورت خطا
    """
    try:
        now = int(datetime.now().timestamp())
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # بررسی وجود جدول special_offers
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='special_offers'")
        if not cursor.fetchone():
            # ایجاد جدول اگر وجود نداشته باشد
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS special_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    offer_type TEXT NOT NULL,
                    discount_amount INTEGER DEFAULT 0,
                    discount_percent INTEGER DEFAULT 0,
                    min_purchase_amount INTEGER DEFAULT 0,
                    required_invites INTEGER DEFAULT 0,
                    usage_limit INTEGER DEFAULT 1,
                    is_public INTEGER DEFAULT 1,
                    is_active INTEGER DEFAULT 1,
                    created_at INTEGER,
                    updated_at INTEGER,
                    expires_at INTEGER
                )
            ''')
            conn.commit()
            logger.info("جدول special_offers ایجاد شد")
        
        # درج رکورد جدید
        cursor.execute('''
            INSERT INTO special_offers (
                title, description, offer_type, discount_amount, discount_percent, 
                min_purchase_amount, required_invites, usage_limit, is_public, 
                is_active, created_at, updated_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            title, description, offer_type, discount_amount, discount_percent, 
            min_purchase_amount, required_invites, usage_limit, is_public, 
            is_active, now, now, expires_at
        ))
        
        # دریافت شناسه رکورد جدید
        offer_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        logger.info(f"پیشنهاد ویژه جدید با شناسه {offer_id} اضافه شد")
        return offer_id
    except Exception as e:
        logger.error(f"خطا در افزودن پیشنهاد ویژه: {e}")
        return None

def update_special_offer(offer_id, title=None, description=None, offer_type=None, 
                        discount_amount=None, discount_percent=None, min_purchase_amount=None, 
                        required_invites=None, usage_limit=None, is_public=None, is_active=None, expires_at=None):
    """
    به‌روزرسانی پیشنهاد ویژه موجود
    """
    try:
        now = int(datetime.now().timestamp())
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # ساخت کوئری به‌روزرسانی بر اساس فیلدهای موجود
        update_fields = []
        values = []
        
        if title is not None:
            update_fields.append("title = ?")
            values.append(title)
        
        if description is not None:
            update_fields.append("description = ?")
            values.append(description)
        
        if offer_type is not None:
            update_fields.append("offer_type = ?")
            values.append(offer_type)
        
        if discount_amount is not None:
            update_fields.append("discount_amount = ?")
            values.append(discount_amount)
        
        if discount_percent is not None:
            update_fields.append("discount_percent = ?")
            values.append(discount_percent)
        
        if min_purchase_amount is not None:
            update_fields.append("min_purchase_amount = ?")
            values.append(min_purchase_amount)
        
        if required_invites is not None:
            update_fields.append("required_invites = ?")
            values.append(required_invites)
        
        if usage_limit is not None:
            update_fields.append("usage_limit = ?")
            values.append(usage_limit)
        
        if is_public is not None:
            update_fields.append("is_public = ?")
            values.append(is_public)
        
        if is_active is not None:
            update_fields.append("is_active = ?")
            values.append(is_active)
        
        if expires_at is not None:
            update_fields.append("expires_at = ?")
            values.append(expires_at)
        
        # اضافه کردن فیلد updated_at
        update_fields.append("updated_at = ?")
        values.append(now)
        
        # اضافه کردن شناسه پیشنهاد به پارامترها
        values.append(offer_id)
        
        # اجرای کوئری به‌روزرسانی
        if update_fields:
            query = f"UPDATE special_offers SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطا در به‌روزرسانی پیشنهاد ویژه: {e}")
        return False

def assign_special_offer_to_user(user_id, offer_id, is_active=1):
    """
    اختصاص پیشنهاد ویژه به کاربر
    """
    try:
        now = int(datetime.now().timestamp())
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # بررسی وجود جدول user_special_offers
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_special_offers'")
        if not cursor.fetchone():
            # ایجاد جدول اگر وجود نداشته باشد
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_special_offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    offer_id INTEGER NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    usage_count INTEGER DEFAULT 0,
                    assigned_at INTEGER,
                    last_used_at INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (offer_id) REFERENCES special_offers (id)
                )
            ''')
            conn.commit()
        
        # بررسی وجود رکورد قبلی برای این کاربر و پیشنهاد
        cursor.execute('SELECT id FROM user_special_offers WHERE user_id = ? AND offer_id = ?', (user_id, offer_id))
        existing = cursor.fetchone()
        
        if existing:
            # به‌روزرسانی رکورد موجود
            cursor.execute('''
                UPDATE user_special_offers 
                SET is_active = ?, assigned_at = ? 
                WHERE user_id = ? AND offer_id = ?
            ''', (is_active, now, user_id, offer_id))
        else:
            # درج رکورد جدید
            cursor.execute('''
                INSERT INTO user_special_offers (user_id, offer_id, is_active, usage_count, assigned_at)
                VALUES (?, ?, ?, 0, ?)
            ''', (user_id, offer_id, is_active, now))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطا در اختصاص پیشنهاد ویژه به کاربر: {e}")
        return False

def set_user_special_offer_active(user_id, offer_id, is_active):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE user_special_offers SET is_active = ? WHERE user_id = ? AND offer_id = ?
        ''', (is_active, user_id, offer_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطا در فعال/غیرفعال کردن پیشنهاد ویژه کاربر: {e}")
        return False

def get_active_special_offers():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, title, description FROM special_offers WHERE is_active = 1
        ''')
        offers = cursor.fetchall()
        conn.close()
        return offers
    except Exception as e:
        logger.error(f"خطا در دریافت پیشنهادات ویژه فعال: {e}")
        return []

def get_user_special_offers(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT so.id, so.title, so.description FROM user_special_offers uso
            JOIN special_offers so ON uso.offer_id = so.id
            WHERE uso.user_id = ? AND uso.is_active = 1 AND so.is_active = 1
        ''', (user_id,))
        offers = cursor.fetchall()
        conn.close()
        return offers
    except Exception as e:
        logger.error(f"خطا در دریافت پیشنهادات ویژه کاربر: {e}")
        return []

def get_all_special_offers():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''SELECT id, title, description, offer_type, discount_amount, discount_percent, 
                          min_purchase_amount, required_invites, usage_limit, is_public, is_active 
                          FROM special_offers ORDER BY created_at DESC''')
        offers = cursor.fetchall()
        conn.close()
        return offers
    except Exception as e:
        logger.error(f"خطا در دریافت همه پیشنهادات ویژه: {e}")
        return []

def get_user_eligible_offers(user_id):
    """
    دریافت پیشنهادات ویژه که کاربر شرایط استفاده از آنها را دارد
    
    Args:
        user_id (int): شناسه کاربر
        
    Returns:
        list: لیست پیشنهادات قابل استفاده
    """
    try:
        now = int(datetime.now().timestamp())
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # دریافت پیشنهادات عمومی فعال
        public_offers = []
        cursor.execute('''
            SELECT id, title, description, offer_type, discount_amount, discount_percent, 
                   min_purchase_amount, required_invites, usage_limit
            FROM special_offers 
            WHERE is_active = 1 AND is_public = 1 
                  AND (expires_at IS NULL OR expires_at > ?)
        ''', (now,))
        public_offers = cursor.fetchall()
        
        # دریافت پیشنهادات اختصاصی فعال کاربر
        cursor.execute('''
            SELECT o.id, o.title, o.description, o.offer_type, o.discount_amount, o.discount_percent, 
                   o.min_purchase_amount, o.required_invites, o.usage_limit, uo.usage_count
            FROM special_offers o
            JOIN user_special_offers uo ON o.id = uo.offer_id
            WHERE uo.user_id = ? AND uo.is_active = 1 AND o.is_active = 1
                  AND (o.expires_at IS NULL OR o.expires_at > ?)
        ''', (user_id, now))
        user_offers = cursor.fetchall()
        
        # برای هر پیشنهاد، بررسی کنیم آیا کاربر شرایط استفاده دارد
        eligible_offers = []
        
        # بررسی پیشنهادات عمومی
        for offer in public_offers:
            (offer_id, title, description, offer_type, discount_amount, 
             discount_percent, min_purchase_amount, required_invites, usage_limit) = offer
            
            # بررسی شرایط پیشنهاد
            if offer_type == 'invite_based':
                # بررسی تعداد دعوت‌ها
                cursor.execute('''
                    SELECT COUNT(*) FROM referrals WHERE inviter_user_id = ?
                ''', (user_id,))
                invite_count = cursor.fetchone()[0]
                
                if invite_count >= required_invites:
                    eligible_offers.append({
                        'id': offer_id,
                        'title': title,
                        'description': description,
                        'offer_type': offer_type,
                        'discount_amount': discount_amount,
                        'discount_percent': discount_percent,
                        'is_public': 1,
                        'usage_count': 0,
                        'usage_limit': usage_limit
                    })
            
            elif offer_type == 'purchase_based':
                # بررسی مجموع خریدها
                cursor.execute('''
                    SELECT SUM(total_price) FROM print_orders 
                    WHERE user_id = ? AND status = 'completed'
                ''', (user_id,))
                total_purchase = cursor.fetchone()[0] or 0
                
                if total_purchase >= min_purchase_amount:
                    eligible_offers.append({
                        'id': offer_id,
                        'title': title,
                        'description': description,
                        'offer_type': offer_type,
                        'discount_amount': discount_amount,
                        'discount_percent': discount_percent,
                        'is_public': 1,
                        'usage_count': 0,
                        'usage_limit': usage_limit
                    })
            
            elif offer_type == 'general':
                # پیشنهاد عمومی بدون شرط
                eligible_offers.append({
                    'id': offer_id,
                    'title': title,
                    'description': description,
                    'offer_type': offer_type,
                    'discount_amount': discount_amount,
                    'discount_percent': discount_percent,
                    'is_public': 1,
                    'usage_count': 0,
                    'usage_limit': usage_limit
                })
        
        # بررسی پیشنهادات اختصاصی کاربر
        for offer in user_offers:
            (offer_id, title, description, offer_type, discount_amount, 
             discount_percent, min_purchase_amount, required_invites, usage_limit, usage_count) = offer
            
            # بررسی تعداد استفاده‌ها
            if usage_count < usage_limit:
                eligible_offers.append({
                    'id': offer_id,
                    'title': title,
                    'description': description,
                    'offer_type': offer_type,
                    'discount_amount': discount_amount,
                    'discount_percent': discount_percent,
                    'is_public': 0,
                    'usage_count': usage_count,
                    'usage_limit': usage_limit
                })
        
        conn.close()
        return eligible_offers
    except Exception as e:
        logger.error(f"خطا در دریافت پیشنهادات ویژه قابل استفاده: {e}")
        return []

def use_special_offer(user_id, offer_id):
    """
    استفاده کاربر از پیشنهاد ویژه
    
    Args:
        user_id (int): شناسه کاربر
        offer_id (int): شناسه پیشنهاد ویژه
        
    Returns:
        bool: True در صورت موفقیت، False در صورت خطا
    """
    try:
        now = int(datetime.now().timestamp())
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # بررسی وجود رکورد قبلی برای این کاربر و پیشنهاد
        cursor.execute('SELECT id, usage_count FROM user_special_offers WHERE user_id = ? AND offer_id = ?', (user_id, offer_id))
        existing = cursor.fetchone()
        
        if existing:
            # به‌روزرسانی رکورد موجود
            user_offer_id, usage_count = existing
            cursor.execute('''
                UPDATE user_special_offers 
                SET usage_count = ?, last_used_at = ? 
                WHERE id = ?
            ''', (usage_count + 1, now, user_offer_id))
        else:
            # بررسی آیا پیشنهاد عمومی است
            cursor.execute('SELECT is_public FROM special_offers WHERE id = ?', (offer_id,))
            offer = cursor.fetchone()
            
            if offer and offer[0] == 1:
                # ایجاد رکورد جدید برای پیشنهاد عمومی
                cursor.execute('''
                    INSERT INTO user_special_offers (user_id, offer_id, is_active, usage_count, assigned_at, last_used_at)
                    VALUES (?, ?, 1, 1, ?, ?)
                ''', (user_id, offer_id, now, now))
            else:
                # پیشنهاد عمومی نیست و کاربر رکوردی ندارد
                conn.close()
                return False
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطا در استفاده از پیشنهاد ویژه: {e}")
        return False

def calculate_discount(total_price, offer_id):
    """
    محاسبه مبلغ تخفیف براساس پیشنهاد ویژه
    
    Args:
        total_price (int): مبلغ کل سفارش (به تومان)
        offer_id (int): شناسه پیشنهاد ویژه
        
    Returns:
        int: مبلغ تخفیف (به تومان)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # دریافت اطلاعات پیشنهاد
        cursor.execute('''
            SELECT discount_amount, discount_percent 
            FROM special_offers 
            WHERE id = ? AND is_active = 1
        ''', (offer_id,))
        
        offer = cursor.fetchone()
        conn.close()
        
        if not offer:
            return 0
        
        discount_amount, discount_percent = offer
        
        # محاسبه تخفیف
        calculated_discount = 0
        
        # تخفیف مبلغی ثابت
        if discount_amount > 0:
            calculated_discount = discount_amount
        
        # تخفیف درصدی
        if discount_percent > 0:
            calculated_discount = int(total_price * discount_percent / 100)
        
        # اگر تخفیف بیشتر از مبلغ کل باشد، به اندازه مبلغ کل تخفیف می‌دهیم
        if calculated_discount > total_price:
            calculated_discount = total_price
        
        return calculated_discount
    except Exception as e:
        logger.error(f"خطا در محاسبه تخفیف: {e}")
        return 0 