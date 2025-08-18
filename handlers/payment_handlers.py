import asyncio
import logging
import os
from datetime import datetime
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.types import InputFile

import config
from config import orders, VIDEO_PATH, CARD_NUMBER, ADMIN_IDS
from keyboards import get_cancel_keyboard, get_ton_connect_keyboard, get_main_menu
from states import CardPaymentStates
from api_utils import get_recipient_address, get_ton_payment_body
from utils import send_order_to_admin, send_card_order_to_admin

logger = logging.getLogger(__name__)

async def get_bot():
    """Get bot instance dynamically to avoid circular imports"""
    from main import bot
    return bot

async def handle_selection(callback_query: types.CallbackQuery, state: FSMContext):
    selection = callback_query.data.replace("select_", "")
    logger.info(f"Пользователь {callback_query.from_user.id} выбрал пакет: {selection}")
    if selection not in config.STAR_PRICES:
        logger.error(f"Пакет {selection} не найден для пользователя {callback_query.from_user.id}")
        await callback_query.answer("❌ Помилка: пакет не знайдено.")
        return
    
    order_data = config.STAR_PRICES[selection]
    
    order_id = f"{order_data['type']}_{callback_query.from_user.id}_{int(datetime.now().timestamp())}"
    username = f"@{callback_query.from_user.username}" if callback_query.from_user.username else callback_query.from_user.full_name
    orders[order_id] = {
        "user_id": callback_query.from_user.id,
        "user_name": username,
        "type": order_data["type"],
        "price": order_data["price"],
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    
    if order_data["type"] == "stars":
        orders[order_id]["stars"] = order_data["stars"]
    else:
        orders[order_id]["months"] = order_data["months"]
    
    await state.update_data(order_id=order_id)
    
    payment_text = f"""💳 Виберіть спосіб оплати:

{'⭐ Кількість зірок: ' + str(order_data['stars']) if order_data['type'] == 'stars' else '💎 Термін: ' + str(order_data['months']) + ' місяців'}
💰 Сума до оплати: {order_data['price']}₴

Доступні способи оплати:
💎 Оплата TON - через TON Connect
💳 Оплата картой"""
    
    logger.info(f"Отображение меню оплаты для заказа {order_id}")
    
    # Import keyboards dynamically to avoid circular imports
    import keyboards
    await callback_query.message.edit_text(payment_text, reply_markup=keyboards.get_payment_method_keyboard(order_id))
    await callback_query.answer()

async def handle_card_payment(callback_query: types.CallbackQuery, state: FSMContext):
    logger.debug(f"Получен callback_query: {callback_query.data} от пользователя {callback_query.from_user.id}")
    bot = await get_bot()
    
    try:
        order_id = callback_query.data.replace("pay_card_", "")
        logger.info(f"Начало обработки оплаты картой для заказа {order_id} пользователем {callback_query.from_user.id}")

        if order_id not in orders:
            logger.error(f"Заказ {order_id} не найден")
            await callback_query.message.answer("❌ Замовлення не знайдено.")
            await callback_query.answer()
            return

        order = orders[order_id]
        order["payment_method"] = "card"
        logger.debug(f"Обновлен заказ: {order}")

        try:
            if os.path.exists(VIDEO_PATH) and os.access(VIDEO_PATH, os.R_OK):
                await bot.send_video(
                    callback_query.from_user.id,
                    video=InputFile(VIDEO_PATH),
                    caption="📹 Приклад оплати картою"
                )
                logger.info(f"Видео отправлено пользователю {callback_query.from_user.id}")
            else:
                logger.warning(f"Видео {VIDEO_PATH} не найдено или недоступно")
                await bot.send_message(callback_query.from_user.id, "📹 Приклад оплати недоступний")
        except Exception as e:
            logger.error(f"Ошибка при отправке видео пользователю {callback_query.from_user.id}: {str(e)}")
            await bot.send_message(callback_query.from_user.id, "📹 Помилка при відправці прикладу оплати")

        payment_text = f"""💳 Оплата картой:

До оплати: {order['price']} грн

📋 Реквізити для оплати:
💳 Номер картки: `{CARD_NUMBER}`

⚠️ Спочатку напишіть свій username (@username) на які мають прийти зірки
💡 Username може містити латинські літери, цифри та підкреслення (_)"""
        
        await callback_query.message.answer(
            payment_text,
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard()
        )
        logger.info(f"Отправлено сообщение с реквизитами и кнопкой отмены пользователю {callback_query.from_user.id}")

        await state.update_data(order_id=order_id)
        await CardPaymentStates.waiting_for_username.set()
        logger.info(f"Состояние установлено: waiting_for_username для пользователя {callback_query.from_user.id}")
        
        await callback_query.answer()

    except Exception as e:
        logger.error(f"Ошибка в handle_card_payment для заказа {order_id}: {str(e)}")
        await callback_query.message.answer("❌ Помилка при обробці оплати картой. Спробуйте ще раз.")
        await callback_query.answer()

async def handle_username_input(message: types.Message, state: FSMContext):
    bot = await get_bot()
    
    try:
        username = message.text.strip()
        logger.debug(f"Получен username: {username} от пользователя {message.from_user.id}")

        data = await state.get_data()
        order_id = data.get('order_id')
        logger.debug(f"Проверка order_id: {order_id}")

        if order_id not in orders:
            logger.error(f"Заказ {order_id} не найден для пользователя {message.from_user.id}")
            await message.answer("❌ Замовлення не знайдено.")
            await state.finish()
            return

        orders[order_id]['customer_username'] = username

        await message.answer(
            f"""✅ Username збережено: {username}

💳 Тепер оплатіть {orders[order_id]['price']} грн на картку:
`{CARD_NUMBER}`

📷 Після оплати надішліть сюди в чат скріншот оплати.""",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard()
        )

        await CardPaymentStates.waiting_for_payment_screenshot.set()
        logger.info(f"Переход в состояние waiting_for_payment_screenshot для пользователя {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка в handle_username_input для пользователя {message.from_user.id}: {str(e)}")
        await message.answer("❌ Помилка при обробці username. Спробуйте ще раз.")
        await state.finish()

async def handle_payment_screenshot(message: types.Message, state: FSMContext):
    try:
        data = await state.get_data()
        order_id = data.get('order_id')
        
        if order_id not in orders:
            await message.answer("❌ Замовлення не знайдено.")
            await state.finish()
            return
        
        # Сохраняем скриншот в заказ
        orders[order_id]['payment_screenshot'] = message.photo[-1].file_id
        orders[order_id]['status'] = 'pending_admin'
        
        await message.answer(
            "✅ Скріншот отримано! Ваше замовлення передано адміністратору на перевірку.\n"
            "⏳ Очікуйте підтвердження (зазвичай до 30 хвилин).",
            reply_markup=get_main_menu()
        )
        
        # Отправляем заказ администратору
        await send_card_order_to_admin(order_id, orders[order_id])
        
        await state.finish()
        logger.info(f"Скриншот оплаты получен от пользователя {message.from_user.id} для заказа {order_id}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки скриншота от пользователя {message.from_user.id}: {str(e)}")
        await message.answer("❌ Помилка при обробці скріншота. Спробуйте ще раз.")
        await state.finish()

async def handle_wrong_content_type(message: types.Message, state: FSMContext):
    await message.answer("❌ Будь ласка, надішліть скріншот оплати (фото), а не текст.")
    logger.warning(f"Пользователь {message.from_user.id} отправил неверный тип контента в состоянии ожидания скриншота")

async def handle_ton_payment(callback_query: types.CallbackQuery, state: FSMContext):
    order_id = callback_query.data.replace("pay_ton_", "")
    logger.info(f"Начало обработки TON-оплаты для заказа {order_id} пользователем {callback_query.from_user.id}")
    
    if order_id not in orders:
        logger.error(f"Заказ {order_id} не найден для пользователя {callback_query.from_user.id}")
        await callback_query.answer("❌ Замовлення не знайдено.")
        return
    
    order = orders[order_id]
    if order.get("status") == "pending_admin":
        logger.info(f"Заказ {order_id} уже ожидает подтверждения администратора")
        await callback_query.message.edit_text("⏳ Замовлення вже на розгляді у адміністратора.")
        await callback_query.answer()
        return
    
    order["payment_method"] = "ton"
    order["status"] = "pending_admin"
    logger.info(f"Детали заказа: {order}")
    
    await callback_query.message.edit_text("⏳ Очікуємо підтвердження адміністратора...")
    await send_order_to_admin(order_id, order, "TON")
    await callback_query.answer()

def register_handlers(dp: Dispatcher):
    dp.register_callback_query_handler(handle_selection, lambda c: c.data.startswith("select_"))
    dp.register_callback_query_handler(handle_card_payment, lambda c: c.data.startswith("pay_card_"))
    dp.register_message_handler(handle_username_input, state=CardPaymentStates.waiting_for_username)
    dp.register_message_handler(handle_payment_screenshot, content_types=['photo'], state=CardPaymentStates.waiting_for_payment_screenshot)
    dp.register_message_handler(handle_wrong_content_type, lambda message: message.content_type != 'photo', state=CardPaymentStates.waiting_for_payment_screenshot)
    dp.register_callback_query_handler(handle_ton_payment, lambda c: c.data.startswith("pay_ton_"))
