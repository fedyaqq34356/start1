import logging
import random

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
from config import ADMIN_IDS
from keyboards import get_main_menu
from utils import subscription_required

logger = logging.getLogger(__name__)

async def get_bot():
    """Get bot instance dynamically to avoid circular imports"""
    from main import bot
    return bot

async def help_command(message: types.Message):
    help_text = """📋 Як купити зірки або Telegram Premium:

1️⃣ Оберіть "Придбати зірки" або "Придбати Telegram Premium" у меню
2️⃣ Виберіть потрібний пакет
3️⃣ Оберіть спосіб оплати (TON или картой)
4️⃣ Очікуйте підтвердження адміністратора
5️⃣ Для оплаты TON: подтвердите транзакцию в кошельке
   Для оплаты картой: отправьте username, затем скриншот оплаты
6️⃣ Очікуйте автоматичного зарахування зірок или преміум-підписки

❓ Якщо у вас виникли питання, натисніть кнопку "Зв'язатися з підтримкою"."""    
    await message.answer(help_text)
    logger.info(f"Пользователь {message.from_user.id} запросил справку")

async def reviews_channel(message: types.Message):
    if not await subscription_required(message.from_user.id):
        return
        
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📣 Перейти до каналу", url="https://t.me/starsZEMSTA"))
    await message.answer("📣 Перегляньте відгуки наших клієнтів у нашому каналі:", reply_markup=keyboard)
    logger.info(f"Пользователь {message.from_user.id} запросил канал с отзывами")

async def support_contact(message: types.Message):
    if not await subscription_required(message.from_user.id):
        return
        
    keyboard = InlineKeyboardMarkup()
    random_admin_id = random.choice(ADMIN_IDS)
    keyboard.add(InlineKeyboardButton("💬 Написати підтримці", url=f"tg://user?id={random_admin_id}"))
    
    await message.answer("🆘 Для зв'язку з підтримкою натисніть кнопку нижче:", reply_markup=keyboard)
    logger.info(f"Користувач {message.from_user.id} запросив підтримку, обраний админ {random_admin_id}")

async def back_to_main_menu(callback_query: types.CallbackQuery):
    await callback_query.message.answer(
        "🔙 Повернення до головного меню:",
        reply_markup=get_main_menu()
    )
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} вернулся в главное меню")

async def cancel_order_by_user(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('order_id')
    if order_id and order_id in config.orders:
        del config.orders[order_id]
        logger.info(f"Заказ {order_id} удален после отмены пользователем {callback_query.from_user.id}")
    await state.finish()
    await callback_query.message.edit_text("❌ Замовлення скасовано.")
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} отменил заказ")

async def cancel_any_state(message: types.Message, state: FSMContext):
    """Универсальная отмена любого состояния"""
    current_state = await state.get_state()
    if current_state:
        data = await state.get_data()
        order_id = data.get('order_id')
        
        # Удаляем заказ если он есть
        if order_id and order_id in config.orders:
            del config.orders[order_id]
            
        await state.finish()
        await message.answer("❌ Операція скасована.", reply_markup=get_main_menu())
        logger.info(f"Пользователь {message.from_user.id} отменил состояние {current_state}")
    else:
        await message.answer("🏠 Ви в головному меню.", reply_markup=get_main_menu())

async def handle_other_messages(message: types.Message):
    if not await subscription_required(message.from_user.id):
        return
        
    await message.answer("❓ Оберіть дію з меню нижче або введіть /help для довідки:", reply_markup=get_main_menu())
    logger.info(f"Пользователь {message.from_user.id} отправил неизвестное сообщение")

def register_handlers(dp: Dispatcher):
    dp.register_message_handler(help_command, commands=['help'])
    dp.register_message_handler(reviews_channel, text="📣 Канал з відгуками")
    dp.register_message_handler(support_contact, text="🆘 Зв'язатися з підтримкою")
    dp.register_callback_query_handler(back_to_main_menu, lambda c: c.data == "back_to_main")
    dp.register_callback_query_handler(cancel_order_by_user, lambda c: c.data == "cancel_order", state="*")
    dp.register_message_handler(cancel_any_state, lambda message: message.text and message.text.lower() in [
        'відміна', 'отмена', 'cancel', '/cancel', '❌ відміна'
    ], state="*")
    dp.register_message_handler(handle_other_messages, lambda message: not message.text.startswith('/'), state=None, content_types=['text'])
