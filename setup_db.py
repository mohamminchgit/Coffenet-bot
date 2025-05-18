import os
import sqlite3
import logging
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

def setup_database(force_recreate=False):
    """
    ایجاد پایگاه داده و جداول مورد نیاز
    
    Args:
        force_recreate (bool): اگر True باشد، پایگاه داده موجود را حذف و از نو ایجاد می‌کند
    """
    try:
        # بررسی وجود فایل دیتابیس
        db_exists = os.path.isfile(DB_PATH)
        
        # حذف پایگاه داده موجود در صورت نیاز
        if db_exists and force_recreate:
            logger.warning("حذف پایگاه داده موجود...")
            os.remove(DB_PATH)
            db_exists = False
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # ایجاد جدول کاربران
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            phone_number TEXT DEFAULT '',
            balance INTEGER DEFAULT 0,
            username TEXT DEFAULT '',
            created_at INTEGER
        )
        ''')
        
        # ایجاد جدول معرفی‌ها
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
        
        # ایجاد جدول تراکنش‌ها
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
        
        conn.commit()
        conn.close()
        
        if db_exists and not force_recreate:
            logger.info("اتصال به پایگاه داده موجود با موفقیت انجام شد")
        else:
            logger.info("پایگاه داده جدید با موفقیت ایجاد شد")
        
        # نمایش جداول موجود
        show_tables()
        
        return True
    except Exception as e:
        logger.error(f"خطا در ایجاد/اتصال به پایگاه داده: {e}")
        return False

def show_tables():
    """نمایش جداول موجود در پایگاه داده"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        logger.info(f"جداول موجود در پایگاه داده: {[table[0] for table in tables]}")
        
        # نمایش ساختار هر جدول
        for table in tables:
            table_name = table[0]
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            logger.info(f"ساختار جدول {table_name}:")
            for column in columns:
                logger.info(f"  {column[1]} ({column[2]})")
        
        conn.close()
    except Exception as e:
        logger.error(f"خطا در نمایش جداول: {e}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='راه‌اندازی پایگاه داده')
    parser.add_argument('--recreate', action='store_true', help='حذف و ایجاد مجدد پایگاه داده')
    args = parser.parse_args()
    
    setup_database(force_recreate=args.recreate) 