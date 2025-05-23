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
        
        # ایجاد جدول پیشنهادات ویژه
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS special_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            is_active INTEGER DEFAULT 1,
            created_at INTEGER,
            updated_at INTEGER
        )
        ''')
        
        # ایجاد جدول ارتباط پیشنهاد با کاربر
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_special_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            offer_id INTEGER NOT NULL,
            is_active INTEGER DEFAULT 1,
            assigned_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (offer_id) REFERENCES special_offers (id)
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

def setup_special_offers_table():
    """
    ایجاد جدول پیشنهادات ویژه اگر وجود نداشته باشد
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # بررسی وجود جدول special_offers قدیمی
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='special_offers'")
        if cursor.fetchone():
            # بررسی ستون‌های موجود
            cursor.execute("PRAGMA table_info(special_offers)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # اگر ستون‌های جدید وجود نداشته باشند، جدول را به‌روزرسانی می‌کنیم
            if "offer_type" not in columns:
                logger.info("به‌روزرسانی جدول special_offers...")
                
                # پشتیبان‌گیری از جدول قدیمی
                cursor.execute("ALTER TABLE special_offers RENAME TO special_offers_old")
                
                # ایجاد جدول جدید با ساختار به‌روز
                cursor.execute('''
                CREATE TABLE special_offers (
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
                
                # انتقال داده‌ها از جدول قدیمی به جدید
                cursor.execute('''
                INSERT INTO special_offers (id, title, description, offer_type, is_active, created_at, updated_at)
                SELECT id, title, description, 'general', is_active, created_at, updated_at FROM special_offers_old
                ''')
                
                conn.commit()
                logger.info("جدول special_offers با موفقیت به‌روزرسانی شد")
        else:
            # ایجاد جدول جدید
            logger.info("ایجاد جدول special_offers...")
            
            # ایجاد جدول پیشنهادات ویژه
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
            logger.info("جدول special_offers با موفقیت ایجاد شد")
        
        # به‌روزرسانی یا ایجاد جدول ارتباط پیشنهاد با کاربر
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_special_offers'")
        if cursor.fetchone():
            # بررسی ستون‌های موجود
            cursor.execute("PRAGMA table_info(user_special_offers)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # اگر ستون‌های جدید وجود نداشته باشند، جدول را به‌روزرسانی می‌کنیم
            if "usage_count" not in columns:
                logger.info("به‌روزرسانی جدول user_special_offers...")
                
                # پشتیبان‌گیری از جدول قدیمی
                cursor.execute("ALTER TABLE user_special_offers RENAME TO user_special_offers_old")
                
                # ایجاد جدول جدید با ساختار به‌روز
                cursor.execute('''
                CREATE TABLE user_special_offers (
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
                
                # انتقال داده‌ها از جدول قدیمی به جدید
                cursor.execute('''
                INSERT INTO user_special_offers (id, user_id, offer_id, is_active, assigned_at)
                SELECT id, user_id, offer_id, is_active, assigned_at FROM user_special_offers_old
                ''')
                
                conn.commit()
                logger.info("جدول user_special_offers با موفقیت به‌روزرسانی شد")
        else:
            # ایجاد جدول جدید
            logger.info("ایجاد جدول user_special_offers...")
            
            # ایجاد جدول ارتباط پیشنهاد با کاربر
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
            logger.info("جدول user_special_offers با موفقیت ایجاد شد")
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطا در به‌روزرسانی/ایجاد جداول پیشنهادات ویژه: {e}")
        return False

def cleanup_old_tables():
    """
    پاک کردن جداول قدیمی با پسوند _old از دیتابیس
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # دریافت لیست جداول با پسوند _old
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_old'")
        old_tables = cursor.fetchall()
        
        if old_tables:
            logger.info(f"در حال حذف {len(old_tables)} جدول قدیمی...")
            
            for table in old_tables:
                table_name = table[0]
                cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                logger.info(f"جدول {table_name} با موفقیت حذف شد")
            
            conn.commit()
            logger.info("تمام جداول قدیمی با موفقیت حذف شدند")
        else:
            logger.info("هیچ جدول قدیمی‌ای برای حذف یافت نشد")
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"خطا در حذف جداول قدیمی: {e}")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='راه‌اندازی پایگاه داده')
    parser.add_argument('--recreate', action='store_true', help='حذف و ایجاد مجدد پایگاه داده')
    parser.add_argument('--only-special-offers', action='store_true', help='فقط به‌روزرسانی جداول پیشنهادات ویژه')
    parser.add_argument('--cleanup', action='store_true', help='پاک کردن جداول قدیمی با پسوند _old')
    args = parser.parse_args()
    
    if args.cleanup:
        cleanup_old_tables()
    elif args.only_special_offers:
        setup_special_offers_table()
    else:
        setup_database(force_recreate=args.recreate)
        setup_special_offers_table() 