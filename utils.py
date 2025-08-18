import asyncio
import logging
from datetime import datetime

from config import ADMIN_IDS, RESTART_ON_ERROR
from keyboards import get_admin_card_approval_keyboard, get_main_menu
from main import bot
import os
import sys

logger = logging.getLogger(__name__)

async def send_order_to_admin(order_id: str, order: dict, payment_method: str):
    order_text = f"""📝 Новый заказ ожидает подтверждения:

👤 Пользователь: {order['user_name']} (@{order['user_id']})
📦 Тип: {'Звезды' if order['type'] == 'stars' else 'Telegram Premium'}
{'⭐ Количество: ' + str(order.get('stars', 'не указано')) if order['type'] == 'stars' else '💎 Срок: ' + str(order.get('months', 'не указано')) + ' месяцев'}
💰 Сумма: {order['price']}₴
💳 Способ оплаты: {payment_method}
🕒 Время: {order['created_at']}

Пожалуйста, подтвердите или отклоните заказ."""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, order_text, reply_markup=get_admin_card_approval_keyboard(order_id))
            logger.info(f"Заказ {order_id} отправлен администратору {admin_id} на подтверждение")
        except Exception as e:
            logger.error(f"Ошибка отправки заказа {order_id} администратору {admin_id}: {e}")

async def send_card_order_to_admin(order_id: str, order: dict):
    try:
        order_text = f"""💳 Новый заказ с оплатой картой:

👤 Пользователь: {order['user_name']} (ID: {order['user_id']})
📝 Username клиента: {order.get('customer_username', 'не указан')}
📦 Тип: {'Звезды' if order['type'] == 'stars' else 'Telegram Premium'}
{'⭐ Количество: ' + str(order.get('stars', 'не указано')) if order['type'] == 'stars' else '💎 Срок: ' + str(order.get('months', 'не указано')) + ' месяцев'}
💰 Сумма: {order['price']}₴
💳 Способ оплаты: Картой
🕒 Время: {order['created_at']}

Скриншот оплаты:"""
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_photo(
                    admin_id,
                    photo=order['payment_screenshot'],
                    caption=order_text,
                    reply_markup=get_admin_card_approval_keyboard(order_id)
                )
                logger.info(f"Заказ с оплатой картой {order_id} отправлен администратору {admin_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки заказа с оплатой картой {order_id} администратору {admin_id}: {e}")
                await bot.send_message(
                    order['user_id'],
                    "❌ Помилка при відправці замовлення адміністратору. Спробуйте ще раз або зв'яжіться з підтримкою.",
                    reply_markup=get_main_menu()
                )
                return
    except Exception as e:
        logger.error(f"Общая ошибка в send_card_order_to_admin для заказа {order_id}: {str(e)}", exc_info=True)
        await bot.send_message(
            order['user_id'],
            "❌ Помилка при обробці замовлення. Спробуйте ще раз або зв'яжіться з підтримкою.",
            reply_markup=get_main_menu()
        )

async def check_split_api_health():
    """Проверка доступности Split API"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {config.SPLIT_API_TOKEN}"}
            async with session.get(f"{config.SPLIT_API_URL}/health", headers=headers, timeout=10) as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"Split API недоступен: {e}")
        return False

async def subscription_required(user_id: int) -> bool:
    if not await start_handlers.check_subscription(user_id):  # Импорт из start_handlers
        subscription_text = """❌ Щоб користуватися ботом, потрібно підписатися на наш основний канал!

📺 Підпишіться на канал і натисніть кнопку "Перевірити підписку" """
        
        await bot.send_message(
            user_id,
            subscription_text,
            reply_markup=keyboards.get_subscription_keyboard()
        )
        logger.info(f"Пользователь {user_id} не подписан, отправлено сообщение о подписке")
        return False
    return True

async def safe_restart():
    logger.info("🔄 Перезапуск бота через 3 секунды...")
    await asyncio.sleep(3)
    
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, "🔄 Бот перезапускається через помилку...")
    except:
        pass
    
    os.execl(sys.executable, sys.executable, *sys.argv)

async def handle_critical_error(exc_type, exc_value, exc_traceback):
    error_message = f"""🚨 КРИТИЧНА ПОМИЛКА:

Type: {exc_type.__name__}
Message: {str(exc_value)}
Traceback: {traceback.format_exc()}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, error_message)
    except:
        pass
    
    logger.critical(error_message)
    
    if RESTART_ON_ERROR:
        await safe_restart()

async def on_startup(dp):
    database.init_db()  # Импорт из database
    logger.info("🚀 Бот запущено успішно!")
    
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, "🚀 Бот запущено та готовий до роботи!")
    except Exception as e:
        logger.error(f"Не вдалося повідомити адміна про запуск: {e}")

async def on_shutdown(dp):
    logger.info("🔴 Бот завершує роботу...")
    
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, "🔴 Бот завершує роботу...")
    except Exception as e:
        logger.error(f"Не вдалося повідомити адміна про завершення: {e}")



        