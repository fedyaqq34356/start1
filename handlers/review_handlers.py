import logging
import sqlite3
from datetime import datetime

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext

from config import REVIEWS_CHANNEL_ID
from keyboards import get_main_menu
from states import ReviewStates

logger = logging.getLogger(__name__)

async def get_bot():
    """Get bot instance dynamically to avoid circular imports"""
    from main import bot
    return bot

async def handle_review_rating(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора рейтинга"""
    if callback_query.data == "skip_review":
        await callback_query.message.edit_text("✅ Дякуємо за покупку!")
        await callback_query.answer()
        await state.finish()
        return
    
    rating = int(callback_query.data.replace("review_", ""))
    
    # Сохраняем рейтинг в состояние
    data = await state.get_data()
    await state.update_data(rating=rating)
    
    await callback_query.message.edit_text(
        f"⭐ Ви обрали оцінку: {rating}/5\n\n"
        "💬 Тепер напишіть ваш відгук (або натисніть /skip щоб пропустити):"
    )
    await ReviewStates.waiting_for_review_text.set()
    await callback_query.answer()

async def handle_review_text(message: types.Message, state: FSMContext):
    """Обработка текста отзыва"""
    review_text = message.text.strip()
    
    if message.text == "/skip":
        review_text = ""
    
    data = await state.get_data()
    rating = data.get('rating', 5)
    order_id = data.get('order_id', '')
    purchase_info = data.get('purchase_info', '')
    
    # Сохраняем отзыв в базу данных
    await save_review(
        user_id=message.from_user.id,
        username=message.from_user.username or message.from_user.full_name,
        rating=rating,
        review_text=review_text,
        order_id=order_id
    )
    
    # Отправляем отзыв в канал
    if REVIEWS_CHANNEL_ID and rating >= 4:  # Отправляем только хорошие отзывы
        await send_review_to_channel(
            rating=rating,
            review_text=review_text,
            username=message.from_user.username or message.from_user.first_name,
            purchase_info=purchase_info
        )
    
    await message.answer(
        "✅ Дякуємо за ваш відгук! Він допоможе нам покращити сервіс.",
        reply_markup=get_main_menu()
    )
    await state.finish()
    logger.info(f"Отзыв сохранен от пользователя {message.from_user.id} с рейтингом {rating}")

async def save_review(user_id: int, username: str, rating: int, review_text: str, order_id: str):
    """Сохранение отзыва в базу данных"""
    try:
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO reviews (user_id, username, rating, review_text, order_id, created_at) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, rating, review_text, order_id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        logger.info(f"Отзыв сохранен в базу данных для пользователя {user_id}")
    except sqlite3.Error as e:
        logger.error(f"Ошибка сохранения отзыва в базу данных: {e}")

async def send_review_to_channel(rating: int, review_text: str, username: str, purchase_info: str):
    """Отправка отзыва в канал"""
    try:
        bot = await get_bot()
        
        stars = "⭐" * rating
        review_message = f"""🌟 Новий відгук від клієнта!

{stars} {rating}/5

👤 Клієнт: {username}
{purchase_info}

💬 Відгук: {review_text if review_text else "Без коментарів"}

✨ Дякуємо за довіру! @ZEMSTA_stars_bot"""

        await bot.send_message(REVIEWS_CHANNEL_ID, review_message)
        logger.info(f"Отзыв отправлен в канал {REVIEWS_CHANNEL_ID}")
    except Exception as e:
        logger.error(f"Ошибка отправки отзыва в канал: {e}")

def register_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(
        handle_review_rating, 
        lambda c: c.data.startswith("review_") or c.data == "skip_review"
    )
    dp.register_message_handler(
        handle_review_text, 
        state=ReviewStates.waiting_for_review_text
    )
