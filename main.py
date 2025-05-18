import os
import logging
from config import BOT_CONFIG

# تنظیم لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """تابع اصلی برای اجرای ربات"""
    logger.info(f"شروع اجرای ربات {BOT_CONFIG['bot-name']}...")
    
    try:
        # اجرای مستقیم ربات
        from bot import main as run_bot
        run_bot()
    except KeyboardInterrupt:
        logger.info("برنامه با دستور کاربر متوقف شد.")
    except Exception as e:
        logger.error(f"خطا در اجرای برنامه: {e}")

if __name__ == "__main__":
    main() 