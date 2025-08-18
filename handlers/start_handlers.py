import logging
from aiogram import types, Dispatcher
from aiogram.types import InputFile

from config import orders, user_ids, MAIN_CHANNEL_ID
from database import save_user
from keyboards import get_main_menu, get_stars_menu, get_premium_menu, get_subscription_keyboard
from utils import subscription_required
from main import bot  # Импорт bot из main, чтобы избежать циклических импортов

logger = logging.getLogger(__name__)

async def start_command(message: types.Message):
    user_id = message.from_user.id
    user_ids.add(user_id)
    save_user(user_id)
    
    if not await subscription_required(message.from_user.id):
        return
    
    welcome_text = """🌟 Ласкаво просимо до @ZEMSTA_stars_bot!
✨ Обирай, купуй і користуйся зірками!

🔥 Економія до 30%!
💎 Оплата TON або ₴ — як зручно.

👇 Натисни кнопки нижче і починай легко! 😊"""
    
    try:
        with open('welcome_image.jpg', 'rb') as photo:
            await message.answer_photo(photo, caption=welcome_text, reply_markup=get_main_menu())
    except FileNotFoundError:
        logger.warning("Файл welcome_image.jpg не найден")
        await message.answer(welcome_text, reply_markup=get_main_menu())
    except Exception as e:
        logger.error(f"Ошибка при отправке изображения: {e}")
        await message.answer(welcome_text, reply_markup=get_main_menu())
    
    logger.info(f"Пользователь {message.from_user.id} запустил бот")

async def stars_menu(message: types.Message):
    logger.info(f"Пользователь {message.from_user.id} запросил меню звезд")
    if not await subscription_required(message.from_user.id):
        logger.warning(f"Пользователь {message.from_user.id} не подписан на канал")
        return
        
    await message.answer(
        "🌟 Придбати зірки можна за такими цінами:",
        reply_markup=get_stars_menu()
    )

async def premium_menu(message: types.Message):
    if not await subscription_required(message.from_user.id):
        return
        
    await message.answer(
        "💎 Придбати Telegram Premium можна за такими цінами:",
        reply_markup=get_premium_menu()
    )

async def check_subscription_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    
    if await check_subscription(user_id):
        await callback_query.message.edit_text(
            "✅ Ви успішно підписалися на канал. Тепер можете користуватися ботом!",
            reply_markup=None
        )
        await bot.send_message(user_id, "🌟Ласкаво просимо! Оберіть дію:", reply_markup=get_main_menu())
        logger.info(f"Пользователь {user_id} прошел проверку подписки")
    else:
        await callback_query.answer("❌ Ви ще не підписалися на канал. Будь ласка, підпишіться та спробуйте знову.")
        logger.warning(f"Пользователь {user_id} не подписан на канал")

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для пользователя {user_id}: {e}")
        return False

def register_handlers(dp: Dispatcher):
    dp.register_message_handler(start_command, commands=['start'])
    dp.register_message_handler(stars_menu, text="🌟 Придбати зірки")
    dp.register_message_handler(premium_menu, text="💎 Придбати Telegram Premium")
    dp.register_callback_query_handler(check_subscription_callback, lambda c: c.data == "check_subscription")