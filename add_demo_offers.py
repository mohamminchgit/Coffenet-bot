#!/usr/bin/env python
# -*- coding: utf-8 -*-

from database import add_special_offer
import logging

# تنظیم لاگینگ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_demo_offers():
    """
    اضافه کردن چند پیشنهاد ویژه نمونه به دیتابیس
    """
    logger.info("در حال اضافه کردن پیشنهادات ویژه نمونه...")
    
    # پیشنهاد عمومی با تخفیف مبلغی
    offer_id1 = add_special_offer(
        title="تخفیف ثابت ۵۰,۰۰۰ تومانی خوش‌آمدگویی",
        description="تخفیف ویژه برای مشتریان جدید - فقط یکبار استفاده",
        offer_type="general",
        discount_amount=50000,
        discount_percent=0,
        usage_limit=1,
        is_public=1,
        is_active=1
    )
    logger.info(f"پیشنهاد عمومی با تخفیف مبلغی اضافه شد. (ID: {offer_id1})")
    
    # پیشنهاد عمومی با تخفیف درصدی
    offer_id2 = add_special_offer(
        title="۲۰٪ تخفیف به مناسبت عید",
        description="تخفیف ویژه به مناسبت فرا رسیدن عید - محدود به ۳ بار استفاده",
        offer_type="general",
        discount_amount=0,
        discount_percent=20,
        usage_limit=3,
        is_public=1,
        is_active=1
    )
    logger.info(f"پیشنهاد عمومی با تخفیف درصدی اضافه شد. (ID: {offer_id2})")
    
    # پیشنهاد مبتنی بر دعوت
    offer_id3 = add_special_offer(
        title="۴۰٪ تخفیف برای دعوت از دوستان",
        description="با دعوت از ۱۰ دوست، این تخفیف ویژه برای شما فعال می‌شود",
        offer_type="invite_based",
        discount_amount=0,
        discount_percent=40,
        required_invites=10,
        usage_limit=1,
        is_public=1,
        is_active=1
    )
    logger.info(f"پیشنهاد مبتنی بر دعوت اضافه شد. (ID: {offer_id3})")
    
    # پیشنهاد مبتنی بر خرید
    offer_id4 = add_special_offer(
        title="تخفیف ۷۰,۰۰۰ تومانی برای خریداران ویژه",
        description="تخفیف ویژه برای کاربرانی که بیش از ۵۰۰,۰۰۰ تومان خرید کرده‌اند",
        offer_type="purchase_based",
        discount_amount=70000,
        discount_percent=0,
        min_purchase_amount=500000,
        usage_limit=1,
        is_public=1,
        is_active=1
    )
    logger.info(f"پیشنهاد مبتنی بر خرید اضافه شد. (ID: {offer_id4})")
    
    # پیشنهاد غیرفعال
    offer_id5 = add_special_offer(
        title="تخفیف ۲۵٪ برای مناسبت خاص (غیرفعال)",
        description="تخفیف ویژه برای مناسبت آینده - فعلاً غیرفعال",
        offer_type="general",
        discount_amount=0,
        discount_percent=25,
        usage_limit=2,
        is_public=1,
        is_active=0
    )
    logger.info(f"پیشنهاد غیرفعال اضافه شد. (ID: {offer_id5})")
    
    # پیشنهاد ترکیبی با تخفیف درصدی و حداقل خرید
    offer_id6 = add_special_offer(
        title="۳۰٪ تخفیف برای خرید بالای ۲۰۰,۰۰۰ تومان",
        description="تخفیف ویژه برای خریدهای بزرگ - قابل استفاده تا ۲ بار",
        offer_type="purchase_based",
        discount_amount=0,
        discount_percent=30,
        min_purchase_amount=200000,
        usage_limit=2,
        is_public=1,
        is_active=1
    )
    logger.info(f"پیشنهاد ترکیبی اضافه شد. (ID: {offer_id6})")
    
    logger.info("تمام پیشنهادات نمونه با موفقیت به دیتابیس اضافه شدند.")

if __name__ == "__main__":
    add_demo_offers() 