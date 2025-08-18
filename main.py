import asyncio
import logging
import os
import sys
import traceback
from datetime import datetime

from aiogram import Bot, Dispatcher, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from config import BOT_TOKEN, RESTART_ON_ERROR, ADMIN_IDS
from database import init_db
from handlers import (
    start_handlers,
    payment_handlers,
    review_handlers,
    admin_handlers,
    other_handlers
)

# Налаштування логування
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Ініціалізація бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

async def on_startup(dp):
    """Initialize database and other startup tasks"""
    logger.info("🔧 Инициализация базы данных...")
    init_db()
    logger.info("✅ База данных инициализирована")
    
    # Запускаем задачу cleanup_old_orders здесь
    from admin_handlers import cleanup_old_orders
    asyncio.create_task(cleanup_old_orders())
    logger.info("✅ Задача cleanup_old_orders запущена")
    
    logger.info("🚀 Бот успешно запущен")

async def on_shutdown(dp):
    """Cleanup on shutdown"""
    logger.info("🛑 Остановка бота...")
    await bot.close()

# Регистрация handlers
start_handlers.register_handlers(dp)
payment_handlers.register_handlers(dp)
review_handlers.register_handlers(dp)
admin_handlers.register_handlers(dp)
other_handlers.register_handlers(dp)

if __name__ == '__main__':
    print("🌟 Telegram Bot для продажу зірок та Telegram Premium")
    print("🚀 Запуск бота...")
    print(f"👤 Адміністратор: {ADMIN_IDS}")
    print(f"🔄 Авто-перезапуск: {'✅' if RESTART_ON_ERROR else '❌'}")
    
    if RESTART_ON_ERROR:
        async def handle_critical_error_wrapper(exc_type, exc_value, exc_traceback):
            from utils import handle_critical_error
            await handle_critical_error(exc_type, exc_value, exc_traceback)
        
        sys.excepthook = lambda exc_type, exc_value, exc_traceback: asyncio.run(
            handle_critical_error_wrapper(exc_type, exc_value, exc_traceback)
        )
    
    try:
        executor.start_polling(
            dp, 
            skip_updates=True,
            on_startup=on_startup,
            on_shutdown=on_shutdown
        )
    except Exception as e:
        logger.critical(f"Критична помилка при запуску: {e}")
        if RESTART_ON_ERROR:
            async def safe_restart_wrapper():
                from utils import safe_restart
                await safe_restart()
            asyncio.run(safe_restart_wrapper())
        else:
            raise
