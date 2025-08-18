import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import orders, ADMIN_IDS, user_ids, REVIEWS_CHANNEL_ID, RESTART_ON_ERROR
from keyboards import get_main_menu
from states import BroadcastStates, ReviewStates
from api_utils import get_recipient_address, get_ton_payment_body
from utils import safe_restart
import keyboards

logger = logging.getLogger(__name__)

async def get_bot():
    """Get bot instance dynamically to avoid circular imports"""
    from main import bot
    return bot

async def handle_admin_card_approval(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        if callback_query.from_user.id not in ADMIN_IDS:
            await callback_query.answer("❌ У вас немає прав для цієї дії.")
            return

        action, order_id = callback_query.data.split("_", 1)
        logger.info(f"Администратор {callback_query.from_user.id} выполняет действие: {action} для заказа {order_id}")

        if order_id not in orders:
            logger.error(f"Заказ {order_id} не найден. Текущее содержимое orders: {orders}")
            await callback_query.message.answer("❌ Замовлення не знайдено.")
            await callback_query.answer()
            return

        order = orders[order_id]
        user_id = order["user_id"]
        payment_method = order.get("payment_method", "card")
        is_text_message = not order.get("payment_screenshot")

        # Формируем детальную информацию о покупке
        purchase_info = ""
        if order["type"] == "stars":
            stars_count = order.get('stars', 'не указано')
            purchase_info = f"🌟 Куплено зірок: {stars_count}\n"
        elif order["type"] == "premium":
            months_count = order.get('months', 'не указано')
            purchase_info = f"💎 Куплено преміум: {months_count} місяців\n"

        bot_instance = await get_bot()

        if action == "approve":
            logger.info(f"Заказ {order_id} подтвержден администратором")
            if is_text_message:
                await callback_query.message.edit_reply_markup(reply_markup=None)
                await callback_query.message.answer("✅ Заказ подтвержден!")
            else:
                await callback_query.message.edit_caption(
                    caption=callback_query.message.caption,
                    reply_markup=None
                )
                await callback_query.message.answer("✅ Оплата картой подтверждена!")

            if payment_method == "ton":
                quantity = order["stars"] if order["type"] == "stars" else order["months"]
                username = order["user_name"]
                recipient_address = await get_recipient_address(order["type"], user_id, username, quantity)
                if not recipient_address:
                    logger.error(f"Не удалось получить адрес для {order['type']} (user_id: {user_id}, username: {username}, quantity: {quantity})")
                    await bot_instance.send_message(
                        user_id,
                        "❌ Помилка отримання адреси для оплати TON. Спробуйте ще раз або зв'яжіться з підтримкою.",
                        reply_markup=get_main_menu()
                    )
                    for admin_id in ADMIN_IDS:
                        await bot_instance.send_message(
                            admin_id,
                            f"⚠️ Помилка API для користувача {username} (ID: {user_id}): не вдалося отримати адрес TON."
                        )
                    await callback_query.answer()
                    return

                transaction_data = await get_ton_payment_body(order["type"], quantity, user_id, username)
                if not transaction_data:
                    logger.error(f"Не удалось получить тело транзакции TON для {order['type']} (user_id: {user_id}, username: {username}, quantity: {quantity})")
                    await bot_instance.send_message(
                        user_id,
                        "❌ Помилка підготовки TON транзакції. Спробуйте ще раз або зв'яжіться з підтримкою.",
                        reply_markup=get_main_menu()
                    )
                    for admin_id in ADMIN_IDS:
                        await bot_instance.send_message(
                            admin_id,
                            f"⚠️ Помилка підготовки транзакції TON для користувача {username} (ID: {user_id})."
                        )
                    await callback_query.answer()
                    return

                payment_text = f"""💎 Оплата через TON Connect:

{'⭐ Кількість зірок: ' + str(order['stars']) if order['type'] == 'stars' else '💎 Термін: ' + str(order['months']) + ' місяців'}
💰 Сума: {order['price']}₴

📱 Натисніть кнопку нижче для оплати через TON Connect
🔒 Безпечна транзакція через блокчейн TON

⚠️ Після підтвердження транзакції в гаманці, зірки/преміум будуть автоматично зараховані на ваш акаунт."""
                try:
                    await bot_instance.send_message(
                        user_id,
                        payment_text,
                        reply_markup=keyboards.get_ton_connect_keyboard(transaction_data, recipient_address)
                    )
                    logger.info(f"Пользователю {user_id} отправлено сообщение с TON Connect для заказа {order_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки TON Connect пользователю {user_id} для заказа {order_id}: {e}")
                    await bot_instance.send_message(
                        user_id,
                        "❌ Помилка відправки посилання TON Connect. Зв'яжіться з підтримкою.",
                        reply_markup=get_main_menu()
                    )
            else:
                store_keyboard = InlineKeyboardMarkup()
                store_keyboard.add(InlineKeyboardButton("🔗 Перейти в магазин", url="https://split.tg/store"))
                for admin_id in ADMIN_IDS:
                    try:
                        await bot_instance.send_message(
                            admin_id,
                            f"✅ Заказ {order_id} обработан. Перейдите в магазин для выполнения:",
                            reply_markup=store_keyboard
                        )
                        logger.info(f"Уведомление администратору {admin_id} отправлено")
                    except Exception as e:
                        logger.error(f"Ошибка уведомления администратора {admin_id}: {e}")

        await callback_query.answer()

    except Exception as e:
        logger.error(f"Ошибка в handle_admin_card_approval для заказа {order_id}: {str(e)}", exc_info=True)
        try:
            if is_text_message:
                await callback_query.message.edit_text("❌ Помилка при обробці. Спробуйте ще раз.")
            else:
                await callback_query.message.edit_caption(caption="❌ Помилка при обробці. Спробуйте ще раз.")
        except Exception as edit_error:
            logger.error(f"Ошибка при редактировании сообщения для заказа {order_id}: {edit_error}", exc_info=True)
            bot_instance = await get_bot()
            for admin_id in ADMIN_IDS:
                await bot_instance.send_message(
                    admin_id,
                    f"⚠️ Помилка обробки заказа {order_id}: {str(e)}"
                )
        await callback_query.answer()

async def send_all_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає прав для використання цієї команди.")
        logger.warning(f"Пользователь {message.from_user.id} попытался выполнить команду /sendall без прав администратора")
        return
    
    text = message.text[9:].strip()
    
    if not text:
        await message.answer("📝 Використання: /sendall <текст повідомлення>")
        return
    
    success_count = 0
    fail_count = 0
    
    await message.answer(f"📡 Розпочинаю розсилку для {len(user_ids)} користувачів...")
    
    bot_instance = await get_bot()
    for user_id in user_ids:
        try:
            await bot_instance.send_message(user_id, text)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            fail_count += 1
            logger.error(f"Помилка відправки користувачу {user_id}: {e}")
    
    await message.answer(f"📊 Розсилка завершена!\n✅ Успішно: {success_count}\n❌ Помилок: {fail_count}")
    logger.info(f"Рассылка завершена: успешно {success_count}, ошибок {fail_count}")

async def stats_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає прав для використання цієї команди.")
        return
    
    stats_text = f"""📊 Статистика бота:

👥 Загальна кількість користувачів: {len(user_ids)}
📋 Активних замовлень: {len(orders)}
🕒 Час роботи: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
📺 Канал відгуків: {REVIEWS_CHANNEL_ID}
🔄 Авто-перезапуск: {'✅' if RESTART_ON_ERROR else '❌'}"""
    
    await message.answer(stats_text)
    logger.info(f"Администратор {message.from_user.id} запросил статистику")

async def start_broadcast(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає прав для використання цієї команди.")
        logger.warning(f"Пользователь {message.from_user.id} попытался выполнить команду рассылки без прав администратора")
        return
    
    await message.answer("📝 Введіть текст для розсилки:")
    await BroadcastStates.waiting_for_broadcast_text.set()

async def handle_broadcast_text(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає прав для використання цієї команди.")
        logger.warning(f"Пользователь {message.from_user.id} попытался выполнить рассылку без прав администратора")
        await state.finish()
        return

    text = message.text.strip()
    
    if not text:
        await message.answer("📝 Текст розсилки не може бути порожнім. Спробуйте ще раз:")
        return
    
    success_count = 0
    fail_count = 0
    
    await message.answer(f"📡 Розпочинаю розсилку для {len(user_ids)} користувачів...")
    
    bot_instance = await get_bot()
    for user_id in user_ids:
        try:
            await bot_instance.send_message(user_id, text)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            fail_count += 1
            logger.error(f"Помилка відправки користувачу {user_id}: {e}")
    
    await message.answer(f"📊 Розсилка завершена!\n✅ Успішно: {success_count}\n❌ Помилок: {fail_count}")
    logger.info(f"Рассылка завершена: успешно {success_count}, ошибок {fail_count}")
    await state.finish()

async def restart_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає прав для використання цієї команди.")
        return
    
    await message.answer("🔄 Перезапускаю бота...")
    logger.info(f"Администратор {message.from_user.id} инициировал перезапуск")
    await safe_restart()

async def cleanup_old_orders():
    """Удаление заказов старше 1 часа"""
    while True:
        try:
            current_time = datetime.now()
            to_remove = []
            
            for order_id, order in orders.items():
                order_time = datetime.fromisoformat(order['created_at'])
                if current_time - order_time > timedelta(hours=1):
                    to_remove.append(order_id)
            
            bot_instance = await get_bot()
            for order_id in to_remove:
                user_id = orders[order_id]['user_id']
                try:
                    await bot_instance.send_message(
                        user_id, 
                        "⏰ Ваше замовлення скасовано через тайм-аут (1 година).",
                        reply_markup=get_main_menu()
                    )
                except:
                    pass
                del orders[order_id]
                logger.info(f"Удален просроченный заказ {order_id}")
                
        except Exception as e:
            logger.error(f"Ошибка очистки заказов: {e}")
            
        await asyncio.sleep(300)  

def register_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(handle_admin_card_approval, lambda c: c.data.startswith("approve_") or c.data.startswith("reject_"))
    dp.register_message_handler(send_all_command, commands=['sendall'])
    dp.register_message_handler(stats_command, commands=['stats'])
    dp.register_message_handler(start_broadcast, text="📤 Розсилка")
    dp.register_message_handler(handle_broadcast_text, state=BroadcastStates.waiting_for_broadcast_text)
    dp.register_message_handler(restart_command, commands=['restart'])
    # Убрали asyncio.create_task(cleanup_old_orders()) отсюда
