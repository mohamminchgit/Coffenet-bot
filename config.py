import os
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی از فایل .env
load_dotenv()

# تنظیمات بات
BOT_CONFIG = {
    "TOKEN": os.getenv("BOT_TOKEN", "7794284252:AAFOha2WHHKYIRTW2Q7eqBHEnSKt3krt378"),
    "bot-name": os.getenv("BOT_NAME", "کافی نت مهدی"),
    "support-username": os.getenv("SUPPORT_USERNAME", "https://t.me/mohamminch"),
    "admin-username": int(os.getenv("ADMIN_USERNAME", "882730020")),
    "ch-username": os.getenv("CHANNEL_USERNAME", "https://t.me/coffenetmehdi"),
    "ch-id": os.getenv("CHANNEL_ID", "-1002496906719"),
    "bot-username": os.getenv("BOT_USERNAME", "test1389chbot"),
    "referal-creadit": os.getenv("REFERAL_CREDIT", "3000"),
    "bot-creator": os.getenv("BOT_CREATOR", "mohamminch"),
    "order-channel-id": os.getenv("ORDER_CHANNEL_ID", "-1002478908922")
}

# تنظیمات پایگاه داده
DB_CONFIG = {
    "db_path": os.getenv("DB_PATH", "coffenet.db")
} 