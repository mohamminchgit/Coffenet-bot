import sqlite3
import os
import sys
import datetime
from config import DB_CONFIG

def format_number_with_commas(number):
    """تابع برای جدا کردن اعداد سه رقم سه رقم"""
    return "{:,}".format(int(number))

def convert_timestamp_to_date(timestamp):
    """تبدیل تایم‌استمپ به تاریخ خوانا"""
    if timestamp:
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    return "نامشخص"

def show_all_users():
    """نمایش تمام کاربران ثبت شده در پایگاه داده"""
    db_path = DB_CONFIG["db_path"]
    
    # بررسی وجود فایل دیتابیس
    if not os.path.isfile(db_path):
        print(f"خطا: فایل پایگاه داده '{db_path}' یافت نشد!")
        print("لطفاً ابتدا برنامه اصلی را اجرا کنید تا پایگاه داده ایجاد شود.")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # بررسی وجود جدول users
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            print("خطا: جدول 'users' در پایگاه داده وجود ندارد!")
            conn.close()
            return
        
        # دریافت تعداد کاربران
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        
        if user_count == 0:
            print("هیچ کاربری در پایگاه داده ثبت نشده است.")
            conn.close()
            return
        
        # دریافت لیست کاربران
        cursor.execute("""
            SELECT u.user_id, u.username, u.phone_number, u.balance, u.created_at,
                   COUNT(r.id) AS referral_count,
                   COALESCE(SUM(r.inviter_cart_amount), 0) AS total_referral_amount
            FROM users u
            LEFT JOIN referrals r ON u.user_id = r.inviter_user_id
            GROUP BY u.user_id
            ORDER BY u.created_at DESC
        """)
        users = cursor.fetchall()
        
        # نمایش اطلاعات کاربران
        print(f"\n===== لیست کاربران ({user_count} کاربر) =====\n")
        print("شناسه کاربری\t| نام کاربری\t| شماره تلفن\t| موجودی\t| تعداد دعوت\t| مبلغ دعوت\t| تاریخ ثبت نام")
        print("-" * 120)
        
        for user in users:
            user_id = user[0]
            username = f"@{user[1]}" if user[1] else "بدون نام کاربری"
            phone = user[2] if user[2] else "ثبت نشده"
            balance = format_number_with_commas(user[3])
            created_at = convert_timestamp_to_date(user[4])
            referral_count = user[5]
            referral_amount = format_number_with_commas(user[6])
            
            print(f"{user_id}\t| {username}\t| {phone}\t| {balance} تومان\t| {referral_count}\t| {referral_amount} تومان\t| {created_at}")
        
        # نمایش آمار کلی
        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM referrals")
        total_referrals = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(inviter_cart_amount + invitee_cart_amount) FROM referrals")
        total_referral_amount = cursor.fetchone()[0] or 0
        
        print("\n===== آمار کلی =====")
        print(f"تعداد کل کاربران: {user_count}")
        print(f"مجموع موجودی کل کاربران: {format_number_with_commas(total_balance)} تومان")
        print(f"تعداد کل معرفی‌ها: {total_referrals}")
        print(f"مجموع مبلغ پرداختی بابت معرفی: {format_number_with_commas(total_referral_amount)} تومان")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"خطا در دسترسی به پایگاه داده: {e}")
    except Exception as e:
        print(f"خطای نامشخص: {e}")

if __name__ == "__main__":
    show_all_users() 