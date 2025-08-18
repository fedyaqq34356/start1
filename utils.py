import asyncio
import logging
import os
import sys

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_IDS, MAIN_CHANNEL_ID

logger = logging.getLogger(__name__)

async def get_bot():
    """Get bot instance dynamically to avoid circular imports"""
    from main import bot
    return bot

async def subscription_required(user_id: int) -> bool:
    """Check if user is subscribed to the main channel"""
    try:
        bot = await get_bot()
        member = await bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
        is_subscribed = member.status in ['member', 'administrator', 'creator']
        
        if not is_subscribed:
            keyboard = InlineKeyboardMarkup()
            keyboard.add(InlineKeyboardButton("📢 Підписатися", url="https://t.me/starsZEMSTA"))
            keyboard.add(InlineKeyboardButton("✅ Перевірити підписку", callback_data="check_subscription"))
            
            await bot.send_message(
                user_id,
                "❌ Для використання бота потрібна підписка на наш канал!\n\n"
                "📢 Підпишіться на канал та натисніть 'Перевірити підписку'",
                reply_markup=keyboard
            )
            return False
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для пользователя {user_id}: {e}")
        return True  # В случае ошибки разрешаем доступ

async def send_order_to_admin(order_id: str, order: dict, payment_method: str):
    """Send order to admin for approval"""
    bot = await get_bot()
    
    order_text = f"""📋 Новый заказ #{order_id}

👤 Пользователь: {order['user_name']} (ID: {order['user_id']})
💰 К оплате: {order['price']}₴
💳 Метод оплаты: {payment_method}

{'⭐ Количество звезд: ' + str(order['stars']) if order['type'] == 'stars' else '💎 Срок: ' + str(order['months']) + ' месяцев'}

⏰ Время создания: {order['created_at']}
🔄 Статус: Ожидает подтверждения"""

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{order_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{order_id}")
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, order_text, reply_markup=keyboard)
            logger.info(f"Заказ {order_id} отправлен админу {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки заказа {order_id} админу {admin_id}: {e}")

async def send_card_order_to_admin(order_id: str, order: dict):
    """Send card payment order with screenshot to admin"""
    bot = await get_bot()
    
    order_text = f"""📋 Оплата картой #{order_id}

👤 Пользователь: {order['user_name']} (ID: {order['user_id']})
📱 Username для зачисления: {order.get('customer_username', 'Не указан')}
💰 К оплате: {order['price']}₴
💳 Метод оплаты: Карта

{'⭐ Количество звезд: ' + str(order['stars']) if order['type'] == 'stars' else '💎 Срок: ' + str(order['months']) + ' месяцев'}

⏰ Время создания: {order['created_at']}
🔄 Статус: Ожидает проверки оплаты"""

    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{order_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{order_id}")
    )
    
    for admin_id in ADMIN_IDS:
        try:
            if order.get('payment_screenshot'):
                await bot.send_photo(
                    admin_id, 
                    photo=order['payment_screenshot'],
                    caption=order_text,
                    reply_markup=keyboard
                )
            else:
                await bot.send_message(admin_id, order_text, reply_markup=keyboard)
            logger.info(f"Заказ с оплатой картой {order_id} отправлен админу {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки заказа с оплатой картой {order_id} админу {admin_id}: {e}")

async def handle_critical_error(exc_type, exc_value, exc_traceback):
    """Handle critical errors"""
    error_msg = f"Критическая ошибка: {exc_type.__name__}: {exc_value}"
    logger.critical(error_msg)
    
    # Notify admins about critical error
    try:
        bot = await get_bot()
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🚨 Критическая ошибка бота!\n\n{error_msg}\n\n🔄 Попытка автоматического перезапуска..."
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить админа {admin_id} об ошибке: {e}")
    except Exception as e:
        logger.error(f"Ошибка при уведомлении администраторов: {e}")
    
    # Wait a bit before restart
    await asyncio.sleep(5)
    await safe_restart()

async def safe_restart():
    """Safely restart the bot"""
    logger.info("🔄 Выполняю безопасный перезапуск...")
    
    try:
        # Close bot session
        bot = await get_bot()
        await bot.session.close()
    except Exception as e:
        logger.error(f"Ошибка при закрытии сессии бота: {e}")
    
    # Restart the process
    os.execv(sys.executable, ['python'] + sys.argv)
