import logging
from datetime import datetime
import sqlite3

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext

from config import orders, REVIEWS_CHANNEL_ID, ADMIN_IDS
from keyboards import get_rating_keyboard, get_review_keyboard, get_main_menu
from states import ReviewStates
from main import bot

logger = logging.getLogger(__name__)

async def leave_review(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text(
        "⭐ Оцініть нашу роботу:",
        reply_markup=get_rating_keyboard()
    )
    await ReviewStates.waiting_for_rating.set()
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} начал процесс оставления отзыва")

async def skip_review(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик пропуска отзыва"""
    await callback_query.message.edit_text("✅ Дякуємо за покупку! Звертайтеся ще! 🌟")
    
    # Очищаем состояние если оно есть
    try:
        await state.finish()
    except:
        pass
    
    user_id = callback_query.from_user.id
    
    # Удаляем завершенные заказы пользователя
    for order_id, order in list(orders.items()):
        if order["user_id"] == user_id and order["status"] == "completed":
            del orders[order_id]
            logger.info(f"Заказ {order_id} удален после пропуска отзыва пользователем {user_id}")
    
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} пропустил отзыв")

async def back_to_review_choice(callback_query: types.CallbackQuery, state: FSMContext):
    """Возврат к выбору - оставить отзыв или пропустить"""
    await callback_query.message.edit_text(
        "🌟 Дякуємо за покупку! Будь ласка, залиште відгук про нашу роботу:",
        reply_markup=get_review_keyboard()
    )
    # Сбрасываем состояние на начальное
    try:
        await state.finish()
    except:
        pass
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} вернулся к выбору отзыва")

async def handle_rating(callback_query: types.CallbackQuery, state: FSMContext):
    rating = int(callback_query.data.split('_')[1])
    await state.update_data(rating=rating)
    
    await callback_query.message.edit_text(
        f"Ваша оцінка: {'⭐' * rating}\n\n💬 Тепер напишіть текст відгуку:"
    )
    await ReviewStates.waiting_for_review.set()
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} выбрал оценку {rating}")

async def handle_review_text(message: types.Message, state: FSMContext):
    try:
        review_text = message.text
        logger.debug(f"Получен текст отзыва: {review_text} от пользователя {message.from_user.id}")
        data = await state.get_data()
        rating = data.get('rating', 5)
        order_id = data.get('order_id')
        logger.debug(f"Данные состояния: rating={rating}, order_id={order_id}")

        # Улучшенная логика получения информации о покупке
        purchase_info = ""
        if order_id and order_id in orders:
            order = orders[order_id]
            if order["type"] == "stars":
                stars_count = order.get('stars', 'не указано')
                purchase_info = f"🌟 Куплено зірок: {stars_count}\n"
            elif order["type"] == "premium":
                months_count = order.get('months', 'не указано')
                purchase_info = f"💎 Куплено преміум: {months_count} місяців\n"
            logger.debug(f"Информация о покупке из активного заказа: {purchase_info}")
        else:
            # Если заказ не найден в активных, попробуем получить из состояния
            purchase_info = data.get('purchase_info', '')
            logger.warning(f"Заказ {order_id} не найден в orders, используется purchase_info из состояния: {purchase_info}")
            
            # Если в состоянии тоже нет информации, попробуем восстановить из order_id
            if not purchase_info and order_id:
                try:
                    # Попытка извлечь информацию из order_id (формат: type_userid_timestamp)
                    parts = order_id.split('_')
                    if len(parts) >= 3:
                        order_type = parts[0]
                        if order_type == "stars":
                            purchase_info = "🌟 Куплено зірок: не вказано\n"
                        elif order_type == "premium":
                            purchase_info = "💎 Куплено преміум: не вказано\n"
                    logger.info(f"Восстановлена базовая информация о покупке из order_id: {purchase_info}")
                except Exception as e:
                    logger.error(f"Ошибка при восстановлении информации из order_id {order_id}: {e}")

        # Если все еще нет информации о покупке, устанавливаем общую
        if not purchase_info:
            purchase_info = "🛒 Покупка в нашем боте\n"
            logger.warning(f"Не удалось определить тип покупки для пользователя {message.from_user.id}, используется общая информация")

        try:
            conn = sqlite3.connect('bot_database.db')
            c = conn.cursor()
            c.execute('''
                INSERT INTO reviews (user_id, username, rating, review_text, order_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                message.from_user.id,
                f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name,
                rating,
                review_text,
                order_id,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))
            conn.commit()
            review_id = c.lastrowid
            logger.info(f"Отзыв сохранен в базе данных с ID {review_id}")
        except sqlite3.Error as e:
            logger.error(f"Ошибка при сохранении отзыва в базе данных: {e}", exc_info=True)
            await message.answer(
                "❌ Помилка при збереженні відгуку. Спробуйте ще раз пізніше.",
                reply_markup=get_main_menu()
            )
            await state.finish()
            return
        finally:
            conn.close()

        # Формирование сообщения для канала с обязательным указанием покупки
        channel_message = f"""⭐ НОВИЙ ВІДГУК #{review_id} ⭐

👤 Користувач: {message.from_user.full_name}
📱 Username: @{message.from_user.username if message.from_user.username else 'не вказано'}
{purchase_info}🌟 Оцінка: {'⭐' * rating}
📝 Відгук: {review_text}

📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

#відгук #зірки #телеграм"""
        
        try:
            await bot.send_message(REVIEWS_CHANNEL_ID, channel_message)
            logger.info(f"Отзыв #{review_id} успешно отправлен в канал {REVIEWS_CHANNEL_ID} с информацией о покупке: {purchase_info.strip()}")
        except Exception as e:
            logger.error(f"Ошибка при отправке отзыва в канал {REVIEWS_CHANNEL_ID}: {e}", exc_info=True)
            await message.answer(
                "❌ Помилка при публікації відгуку в канал. Спробуйте ще раз пізніше.",
                reply_markup=get_main_menu()
            )
            await state.finish()
            return

        try:
            await message.answer(
                "✅ Дякуємо за відгук! Він опубліковано в нашому каналі відгуків.",
                reply_markup=get_main_menu()
            )
            logger.info(f"Уведомление пользователю {message.from_user.id} отправлено")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления пользователю {message.from_user.id}: {e}", exc_info=True)

        try:
            for admin_id in ADMIN_IDS:
                admin_message = f"💬 Новий відгук #{review_id} від {message.from_user.full_name} ({rating}/5 зірок)\n{purchase_info.strip()}"
                await bot.send_message(admin_id, admin_message)
            logger.info(f"Уведомление администраторам {ADMIN_IDS} отправлено с информацией о покупке")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления администраторам {ADMIN_IDS}: {e}", exc_info=True)

        if order_id and order_id in orders:
            del orders[order_id]
            logger.info(f"Заказ {order_id} удален после успешного отзыва")

        logger.info(f"Отзыв #{review_id} от пользователя {message.from_user.id} успешно обработан с информацией о покупке")

    except Exception as e:
        logger.error(f"Общая ошибка в handle_review_text для пользователя {message.from_user.id}: {str(e)}", exc_info=True)
        await message.answer(
            "❌ Помилка при обробці відгуку. Спробуйте ще раз пізніше.",
            reply_markup=get_main_menu()
        )
    
    finally:
        await state.finish()
        logger.debug(f"Состояние завершено для пользователя {message.from_user.id}")

def register_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(leave_review, lambda c: c.data == 'leave_review')
    dp.register_callback_query_handler(skip_review, lambda c: c.data == 'skip_review')
    dp.register_callback_query_handler(back_to_review_choice, lambda c: c.data == 'back_to_review_choice')
    dp.register_callback_query_handler(handle_rating, lambda c: c.data.startswith('rate_'), state=ReviewStates.waiting_for_rating)
    dp.register_message_handler(handle_review_text, state=ReviewStates.waiting_for_review)




    