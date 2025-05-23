#!/usr/bin/env python
# -*- coding: utf-8 -*-

from database import get_all_special_offers

def format_number_with_commas(number):
    return "{:,}".format(int(number))

def check_offers():
    """
    نمایش پیشنهادات ویژه موجود در دیتابیس
    """
    offers = get_all_special_offers()
    
    if not offers:
        print("هیچ پیشنهاد ویژه‌ای در دیتابیس وجود ندارد.")
        return
    
    print(f"تعداد کل پیشنهادات ویژه: {len(offers)}")
    print("=" * 50)
    
    for offer in offers:
        offer_id, title, description, offer_type, discount_amount, discount_percent, min_purchase, required_invites, usage_limit, is_public, is_active = offer
        
        status = "🟢 فعال" if is_active else "🟡 غیرفعال"
        offer_type_text = {
            "general": "عمومی",
            "invite_based": "بر اساس دعوت",
            "purchase_based": "بر اساس خرید"
        }.get(offer_type, "نامشخص")
        
        print(f"شناسه: {offer_id}")
        print(f"عنوان: {title}")
        print(f"وضعیت: {status}")
        print(f"نوع: {offer_type_text}")
        
        if discount_amount > 0:
            print(f"مبلغ تخفیف: {format_number_with_commas(discount_amount)} تومان")
        if discount_percent > 0:
            print(f"درصد تخفیف: {discount_percent}٪")
            
        if offer_type == "invite_based":
            print(f"تعداد دعوت لازم: {required_invites}")
        elif offer_type == "purchase_based":
            print(f"حداقل خرید: {format_number_with_commas(min_purchase)} تومان")
            
        print(f"محدودیت استفاده: {usage_limit} بار")
        print(f"توضیحات: {description}")
        print("-" * 50)

if __name__ == "__main__":
    check_offers() 