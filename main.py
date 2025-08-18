import asyncio
import logging
import os
import sys
import traceback
from datetime import datetime

from aiogram import Bot, Dispatcher, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from config import BOT_TOKEN, RESTART_ON_ERROR, ADMIN_IDS
from handlers import (
    start_handlers,
    payment_handlers,
    review_handlers,
    admin_handlers,
    other_handlers
)
from utils import handle_critical_error, safe_restart, on_startup, on_shutdown

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

# Регистрация handlers (импортируем модули, они сами регистрируют обработчики через dp)
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
        sys.excepthook = lambda exc_type, exc_value, exc_traceback: asyncio.run(
            handle_critical_error(exc_type, exc_value, exc_traceback)
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
            asyncio.run(safe_restart())
        else:
            raise