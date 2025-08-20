import asyncio
import logging
import aiohttp
import os
import sys
import traceback
import sqlite3
import random
from datetime import datetime
from typing import Optional, Dict
from aiogram.types import InputFile
import asyncio
from datetime import datetime, timedelta


from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.dispatcher.filters import Text

from dotenv import load_dotenv
import re
# Налаштування логування
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Конфігурація з змінних оточення
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID_RAW = os.getenv('ADMIN_ID', '0')
try:
    ADMIN_IDS = [int(x.strip()) for x in ADMIN_ID_RAW.split(",") if x.strip()]
except ValueError:
    logger.error(f"❌ Некорректное значение ADMIN_ID: '{ADMIN_ID_RAW}'. Ожидаются целые числа через запятую.")
    exit(1)

SPLIT_API_TOKEN = os.getenv('SPLIT_API_TOKEN')
SPLIT_API_URL = os.getenv('SPLIT_API_URL')
REVIEWS_CHANNEL_ID = int(os.getenv('REVIEWS_CHANNEL_ID', '0'))
RESTART_ON_ERROR = os.getenv('RESTART_ON_ERROR', 'true').lower() == 'true'
MAIN_CHANNEL_ID = int(os.getenv('MAIN_CHANNEL_ID', '0'))
CARD_NUMBER = os.getenv('CARD_NUMBER')
VIDEO_PATH = "payment_example.mp4"

# Перевірка наявності необхідних змінних
if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE' or not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не встановлено!")
    exit(1)

if ADMIN_IDS == 0:
    logger.warning("⚠️ ADMIN_ID не встановлено, використовується значення за замовчуванням")

if not CARD_NUMBER:
    logger.error("❌ CARD_NUMBER не встановлено в змінних оточення!")
    exit(1)

if not REVIEWS_CHANNEL_ID:
    logger.error("❌ REVIEWS_CHANNEL_ID не встановлено в змінних оточення!")
    exit(1)

# Ініціалізація бази даних
def init_db():
    try:
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        # Создание таблиц
        c.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                rating INTEGER,
                review_text TEXT,
                order_id TEXT,
                created_at TEXT,
                username TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY
            )
        ''')
        c.execute("PRAGMA table_info(reviews)")
        columns = [info[1] for info in c.fetchall()]
        if 'username' not in columns:
            c.execute('ALTER TABLE reviews ADD COLUMN username TEXT')
        if 'order_id' not in columns:
            c.execute('ALTER TABLE reviews ADD COLUMN order_id TEXT')

        # Проверка существующих отзывов с id >= 60
        c.execute("SELECT COUNT(*) FROM reviews WHERE id >= 80")
        conflict_count = c.fetchone()[0]
        if conflict_count == 0:  # Только если нет конфликтующих записей
            # Установка начального значения автоинкремента на 59 (следующий будет 60)
            c.execute("SELECT seq FROM sqlite_sequence WHERE name='reviews'")
            result = c.fetchone()
            if result is None:
                c.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('reviews', 79)")
                logger.info("Автоинкремент для reviews установлен на 79 (следующий ID будет 80)")
            else:
                # Обновляем только если текущее значение меньше 59
                if result[0] < 79:
                    c.execute("UPDATE sqlite_sequence SET seq = 79 WHERE name = 'reviews'")
                    logger.info("Автоинкремент для reviews обновлен на 79 (следующий ID будет 80)")
                else:
                    logger.info(f"Автоинкремент уже установлен на {result[0]}, не изменяем")

        conn.commit()
        logger.info("База данных успешно инициализирована")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
    except ValueError as ve:
        logger.error(str(ve))
    finally:
        conn.close()

# ДОБАВИТЬ этот обработчик в код:



# Функция для загрузки пользователей из базы данных
def load_users():
    try:
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        user_ids = {row[0] for row in c.fetchall()}
        conn.close()
        return user_ids
    except sqlite3.Error as e:
        logger.error(f"Ошибка при загрузке пользователей из базы данных: {e}")
        return set()

# Функция для сохранения пользователя в базу данных
def save_user(user_id: int):
    try:
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"Пользователь {user_id} сохранен в базе данных")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при сохранении пользователя {user_id} в базе данных: {e}")

# Ініціалізація бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Состояния для оплаты картой
class CardPaymentStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_payment_screenshot = State()

# Стани для FSM
class ReviewStates(StatesGroup):
    waiting_for_review = State()
    waiting_for_rating = State()

# Состояния для рассылки
class BroadcastStates(StatesGroup):
    waiting_for_broadcast_text = State()

# Зберігання користувачів для розсилки
user_ids = load_users()

# Ціни на зірки та Telegram Premium
STAR_PRICES = {
    "50⭐ – 42.5₴": {"stars": 50, "price": 42.5, "type": "stars"},
    "100⭐ – 85₴": {"stars": 100, "price": 85, "type": "stars"},
    "200⭐ – 170₴": {"stars": 200, "price": 170, "type": "stars"},
    "300⭐ – 255₴": {"stars": 300, "price": 255, "type": "stars"},
    "400⭐ – 340₴": {"stars": 400, "price": 340, "type": "stars"},
    "500⭐ – 410₴": {"stars": 500, "price": 410, "type": "stars"},  # ИЗМЕНЕНО С 390
    "1000⭐ – 825₴": {"stars": 1000, "price": 825, "type": "stars"},
    "10000⭐ – 8150₴": {"stars": 10000, "price": 8150, "type": "stars"},  # ДОБАВЛЕНО
    "3 місяці💎 – 669₴": {"months": 3, "price": 669, "type": "premium"},
    "6 місяців💎 – 999₴": {"months": 6, "price": 999, "type": "premium"},
    "12 місяців💎 – 1699₴": {"months": 12, "price": 1699, "type": "premium"},
}

# Тимчасове зберігання замовлень
orders = {}

def get_main_menu(user_id: int | None = None) -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("🌟 Придбати зірки"))
    keyboard.add(KeyboardButton("💎 Придбати Telegram Premium"))
    keyboard.add(KeyboardButton("💻 Зв'язатися з підтримкою"))
    keyboard.add(KeyboardButton("📣 Канал з відгуками"))

    if user_id is not None and user_id in ADMIN_IDS:
        keyboard.add(KeyboardButton("📤 Розсилка"))

    return keyboard

def get_stars_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("50⭐ – 42.5₴", callback_data="select_50⭐ – 42.5₴"),
        InlineKeyboardButton("100⭐ – 85₴", callback_data="select_100⭐ – 85₴"),
        InlineKeyboardButton("200⭐ – 170₴", callback_data="select_200⭐ – 170₴"),
        InlineKeyboardButton("300⭐ – 255₴", callback_data="select_300⭐ – 255₴"),
        InlineKeyboardButton("400⭐ – 340₴", callback_data="select_400⭐ – 340₴"),
        InlineKeyboardButton("500⭐ – 410₴", callback_data="select_500⭐ – 410₴"),  # ИЗМЕНЕНО
        InlineKeyboardButton("1000⭐ – 825₴", callback_data="select_1000⭐ – 825₴"),
        InlineKeyboardButton("10000⭐ – 8150₴", callback_data="select_10000⭐ – 8150₴")  # ДОБАВЛЕНО
    )
    keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main"))
    return keyboard

def get_premium_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("3 місяці💎 – 669₴", callback_data="select_3 місяці💎 – 669₴"),
        InlineKeyboardButton("6 місяців💎 – 999₴", callback_data="select_6 місяців💎 – 999₴"),
        InlineKeyboardButton("12 місяців💎 – 1699₴", callback_data="select_12 місяців💎 – 1699₴")
    )
    keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main"))
    return keyboard

def get_payment_method_keyboard(order_id: str):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("💳 Сплатити карткою", callback_data=f"pay_card_{order_id}")
    )
    keyboard.add(
        InlineKeyboardButton("💎 Сплатити TON", callback_data=f"pay_ton_{order_id}")
    )
    keyboard.add(InlineKeyboardButton("❌ Відміна", callback_data="cancel_order"))
    return keyboard

def get_admin_card_approval_keyboard(order_id: str):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("✅ Підтвердити", callback_data=f"approve_{order_id}"),
        InlineKeyboardButton("❌ Відмінити", callback_data=f"reject_{order_id}")
    )
    return keyboard

def get_review_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("⭐ Залишити відгук", callback_data="leave_review"),
    )
    return keyboard

def get_rating_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("⭐", callback_data="rate_1"),
        InlineKeyboardButton("⭐⭐", callback_data="rate_2"),
        InlineKeyboardButton("⭐⭐⭐", callback_data="rate_3"),
        InlineKeyboardButton("⭐⭐⭐⭐", callback_data="rate_4"),
        InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="rate_5")
    )
    return keyboard

def get_subscription_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📺 Підписатися", url=f"https://t.me/starsZEMSTA_news"))
    keyboard.add(InlineKeyboardButton("✅ Перевірити підписку", callback_data="check_subscription"))
    return keyboard

def get_ton_connect_keyboard(transaction_data: Dict, recipient_address: str):
    keyboard = InlineKeyboardMarkup()
    ton_connect_url = f"ton://transfer/{recipient_address}"
    params = []
    if transaction_data.get('messages'):
        message = transaction_data.get('messages', [{}])[0]
        if message.get('amount'):
            params.append(f"amount={message['amount']}")
        if message.get('payload'):
            params.append(f"bin={message['payload']}")
    if params:
        ton_connect_url += "?" + "&".join(params)
    keyboard.add(InlineKeyboardButton("💎 Оплатить через TON Connect", url=ton_connect_url))
    keyboard.add(InlineKeyboardButton("❌ Отмена", callback_data="cancel_order"))
    return keyboard

def get_cancel_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("❌ Відміна", callback_data="cancel_order"))
    return keyboard

async def get_recipient_address(service_type: str, user_id: int, username: str, quantity: int = 1) -> Optional[str]:
    logger.info(f"Запрос адреса для {service_type} (user_id: {user_id}, username: {username}, quantity: {quantity})")
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {SPLIT_API_TOKEN}",
                "Content-Type": "application/json"
            }
            endpoint = f"/buy/{'premium' if service_type == 'premium' else 'stars'}"
            data = {
                "user_id": user_id,
                "username": username
            }
            if service_type == "premium":
                data["months"] = quantity
            else:
                data["quantity"] = quantity
            logger.info(f"Отправка запроса к {SPLIT_API_URL}{endpoint} с данными: {data}")
            async with session.post(
                f"{SPLIT_API_URL}{endpoint}",
                headers=headers,
                json=data,
                timeout=30
            ) as response:
                logger.info(f"Ответ API: статус {response.status}")
                if response.status == 200:
                    response_data = await response.json()
                    logger.info(f"Получен ответ: {response_data}")
                    try:
                        address = response_data.get('message', {}).get('transaction', {}).get('messages', [{}])[0].get('address')
                        if not address:
                            logger.error(f"Поле 'address' отсутствует в ответе API: {response_data}")
                            return None
                        return address
                    except (KeyError, IndexError) as e:
                        logger.error(f"Ошибка при извлечении адреса из ответа API: {e}, ответ: {response_data}")
                        return None
                else:
                    response_text = await response.text()
                    logger.error(f"❌ Помилка отримання адреси: {response.status}, текст: {response_text}")
                    return None
    except Exception as e:
        logger.error(f"❌ Виняток при отриманні адреси: {str(e)}")
        return None



async def get_ton_payment_body(service_type: str, quantity: int, user_id: int, username: str, inviter_wallet: str = None) -> Optional[Dict]:
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {SPLIT_API_TOKEN}",
                "Content-Type": "application/json"
            }
            endpoint = f"/buy/{'premium' if service_type == 'premium' else 'stars'}"
            data = {
                "user_id": user_id,
                "username": username
            }
            if service_type == "premium":
                data["months"] = quantity
            else:
                data["quantity"] = quantity
            if inviter_wallet:
                data["inviter_wallet"] = inviter_wallet
            logger.info(f"Отправка запроса к {SPLIT_API_URL}{endpoint} для TON с данными: {data}")
            async with session.post(
                f"{SPLIT_API_URL}{endpoint}",
                headers=headers,
                json=data,
                timeout=30
            ) as response:
                logger.info(f"Ответ API: статус {response.status}")
                if response.status == 200:
                    response_data = await response.json()
                    logger.info(f"Получен ответ: {response_data}")
                    try:
                        transaction = response_data.get('message', {}).get('transaction', {})
                        if not transaction:
                            logger.error(f"Поле 'transaction' отсутствует в ответе API: {response_data}")
                            return None
                        return transaction
                    except (KeyError, IndexError) as e:
                        logger.error(f"Ошибка при извлечении тела транзакции из ответа API: {e}, ответ: {response_data}")
                        return None
                else:
                    response_text = await response.text()
                    logger.error(f"Помилка отримання тіла транзакции TON: {response.status}, текст: {response_text}")
                    return None
    except Exception as e:
        logger.error(f"Помилка отримання тіла транзакции TON: {e}")
        return None

async def send_order_to_admin(order_id: str, order: Dict, payment_method: str):
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

async def send_card_order_to_admin(order_id: str, order: Dict):
    try:
        order_text = f"""💳 Новый заказ с оплатой картой:

👤 Пользователь: {order['user_name']} (ID: {order['user_id']})
📝 Username клиента: @{order.get('customer_username', 'не указан')}
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

@dp.callback_query_handler(lambda c: c.data.startswith("pay_card_"))
async def handle_card_payment(callback_query: types.CallbackQuery, state: FSMContext):
    logger.debug(f"Получен callback_query: {callback_query.data} от пользователя {callback_query.from_user.id}")
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



        payment_text = f"""✨Вкажіть @username (тег), на який треба відправити зірки.

⚠️Обов'язково перевірте, що ви вказали правильний нік!"""

        
        await callback_query.message.answer(
            payment_text,
            parse_mode="HTML",
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


@dp.message_handler(state=CardPaymentStates.waiting_for_username)
async def handle_username_input(message: types.Message, state: FSMContext):
    try:
        username = message.text.strip()
        logger.debug(f"Получен username: {username} от пользователя {message.from_user.id}")

        # Валидация username
        if not username:
            await message.answer("❌ Username не може бути порожнім. Спробуйте ще раз:")
            return

        # Убираем @ если пользователь его добавил
        if username.startswith('@'):
            username = username[1:]

        # Проверка формата username (латиница, цифры, подчеркивания, длина 5-32 символа)
        if not re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
            await message.answer(
                "❌ Неправильний формат username!\n\n"
                "Username повинен:\n"
                "• Містити тільки латинські літери (a-z, A-Z)\n"
                "• Цифри (0-9)\n"
                "• Підкреслення (_)\n"
                "• Бути довжиною від 5 до 32 символів\n"
                "• Не містити пробілів та спецсимволів\n\n"
                "Приклад: user_name або UserName123\n"
                "Спробуйте ще раз:"
            )
            return

        data = await state.get_data()
        order_id = data.get('order_id')
        logger.debug(f"Проверка order_id: {order_id}")

        if not order_id or order_id not in orders:
            logger.error(f"Заказ {order_id} не найден для пользователя {message.from_user.id}")
            await message.answer("❌ Замовлення не знайдено.")
            await state.finish()
            return

        # Сохраняем username в заказ
        orders[order_id]['customer_username'] = username
        logger.info(f"Username {username} сохранен для заказа {order_id}")

        await message.answer(
            f"💳 Банк України\n"
            f"Карта: {CARD_NUMBER}\n\n"
            f"💰 До оплати: {orders[order_id]['price']:.2f} UAH\n\n"
            f"⚙️Зірки на аккаунт: @{username}\n"
            f"⭐️@{username} отримає: {orders[order_id]['stars']} ⭐️\n\n"
            f"📸 Після оплати, відправте сюди в чат квитанцію оплати:",
            reply_markup=get_cancel_keyboard()
        )

        await CardPaymentStates.waiting_for_payment_screenshot.set()
        logger.info(f"Переход в состояние waiting_for_payment_screenshot для пользователя {message.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка в handle_username_input для пользователя {message.from_user.id}: {str(e)}")
        await message.answer(
            "❌ Помилка при обробці username. Спробуйте ще раз або натисніть '❌ Відміна' для скасування.",
            reply_markup=get_cancel_keyboard()
        )
        # НЕ завершаем состояние, даем пользователю еще попытку
        
async def check_split_api_health():
    """Проверка доступности Split API"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {SPLIT_API_TOKEN}"}
            async with session.get(f"{SPLIT_API_URL}/health", headers=headers, timeout=10) as response:
                return response.status == 200
    except Exception as e:
        logger.error(f"Split API недоступен: {e}")
        return False

@dp.callback_query_handler(lambda c: c.data.startswith("approve_") or c.data.startswith("reject_"))
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
                    await bot.send_message(
                        user_id,
                        "❌ Помилка отримання адреси для оплати TON. Спробуйте ще раз або зв'яжіться з підтримкою.",
                        reply_markup=get_main_menu()
                    )
                    for admin_id in ADMIN_IDS:
                        await bot.send_message(
                            admin_id,
                            f"⚠️ Помилка API для користувача {username} (ID: {user_id}): не удалось получить адрес TON."
                        )
                    await callback_query.answer()
                    return

                transaction_data = await get_ton_payment_body(order["type"], quantity, user_id, username)
                if not transaction_data:
                    logger.error(f"Не удалось получить тело транзакции TON для {order['type']} (user_id: {user_id}, username: {username}, quantity: {quantity})")
                    await bot.send_message(
                        user_id,
                        "❌ Помилка підготовки TON транзакції. Спробуйте ще раз або зв'яжіться з підтримкою.",
                        reply_markup=get_main_menu()
                    )
                    for admin_id in ADMIN_IDS:
                        await bot.send_message(
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
                    await bot.send_message(
                        user_id,
                        payment_text,
                        reply_markup=get_ton_connect_keyboard(transaction_data, recipient_address)
                    )
                    logger.info(f"Пользователю {user_id} отправлено сообщение с TON Connect для заказа {order_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки TON Connect пользователю {user_id} для заказа {order_id}: {e}")
                    await bot.send_message(
                        user_id,
                        "❌ Помилка відправки посилання TON Connect. Зв'яжіться з підтримкою.",
                        reply_markup=get_main_menu()
                    )
            else:
                store_keyboard = InlineKeyboardMarkup()
                store_keyboard.add(InlineKeyboardButton("🔗 Перейти в магазин", url="https://split.tg/store"))
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"✅ Заказ {order_id} обработан. Перейдите в магазин для выполнения:",
                            reply_markup=store_keyboard
                        )
                        logger.info(f"Уведомление администратору {admin_id} отправлено для заказа {order_id}")
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления администратору {admin_id} для заказа {order_id}: {e}")

                try:
                    await bot.send_message(
                        user_id,
                        "✅ Ваша оплата підтверджена!\n💫 Замовлення обробляється.\n\n‼️ Це займе від 5 хвилин, до 2 годин.",
                        reply_markup=get_main_menu()
                    )
                    
                    # Создаем новое состояние и сохраняем информацию о покупке
                    review_state = FSMContext(storage, chat=user_id, user=user_id)
                    await review_state.update_data(order_id=order_id, purchase_info=purchase_info)
                    
                    await bot.send_message(
                        user_id,
                        "🌟 Дякуємо за покупку! Будь ласка, залиште відгук про нашу роботу:",
                        reply_markup=get_review_keyboard()
                    )
                    logger.info(f"Уведомления пользователю {user_id} отправлены для заказа {order_id} с информацией о покупке: {purchase_info.strip()}")
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю {user_id} для заказа {order_id}: {e}")

                order["status"] = "completed"
                logger.info(f"Заказ {order_id} завершен, но сохраняется для отзыва с информацией: {purchase_info.strip()}")

        else:
            logger.info(f"Заказ {order_id} отклонен администратором")
            if is_text_message:
                await callback_query.message.edit_text("❌ Заказ отклонен.")
            else:
                await callback_query.message.edit_caption(caption="❌ Оплата картой отклонена.")
            try:
                await bot.send_message(
                    user_id,
                    "❌ Ваша оплата була відхилена адміністратором. Зв'яжіться з підтримкою для з'ясування причин.",
                    reply_markup=get_main_menu()
                )
                logger.info(f"Уведомление об отклонении отправлено пользователю {user_id} для заказа {order_id}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления об отклонении пользователю {user_id} для заказа {order_id}: {e}")
            del orders[order_id]
            logger.info(f"Заказ {order_id} удален из orders")

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
            for admin_id in ADMIN_IDS:
                await bot.send_message(
                    admin_id,
                    f"⚠️ Помилка обробки заказа {order_id}: {str(e)}"
                )
        await callback_query.answer()

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
            
            for order_id in to_remove:
                user_id = orders[order_id]['user_id']
                try:
                    await bot.send_message(
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

@dp.callback_query_handler(lambda c: c.data.startswith("pay_ton_"))
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

@dp.callback_query_handler(lambda c: c.data == 'leave_review')
async def start_review(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text(
        "⭐ Оцініть нашу роботу:",
        reply_markup=get_rating_keyboard()
    )
    await ReviewStates.waiting_for_rating.set()
    logger.info(f"Пользователь {callback_query.from_user.id} начал процесс оставления отзыва")

@dp.callback_query_handler(lambda c: c.data == 'skip_review')
async def skip_review(callback_query: types.CallbackQuery):
    await callback_query.message.edit_text("✅ Дякуємо за покупку! Звертайтеся ще! 🌟")
    user_id = callback_query.from_user.id
    for order_id, order in list(orders.items()):
        if order["user_id"] == user_id and order["status"] == "completed":
            del orders[order_id]
            logger.info(f"Заказ {order_id} удален после пропуска отзыва пользователем {user_id}")
    logger.info(f"Пользователь {callback_query.from_user.id} пропустил отзыв")

@dp.callback_query_handler(lambda c: c.data.startswith('rate_'), state=ReviewStates.waiting_for_rating)
async def handle_rating(callback_query: types.CallbackQuery, state: FSMContext):
    rating = int(callback_query.data.split('_')[1])
    await state.update_data(rating=rating)
    
    await callback_query.message.edit_text(
        f"Ваша оцінка: {'⭐' * rating}\n\n💬 Тепер напишіть текст відгуку:"
    )
    await ReviewStates.waiting_for_review.set()
    logger.info(f"Пользователь {callback_query.from_user.id} выбрал оценку {rating}")

@dp.message_handler(state=ReviewStates.waiting_for_review)
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

@dp.message_handler(lambda message: message.text and message.text.lower() in [
    'відміна', 'отмена', 'cancel', '/cancel', '❌ відміна'
], state="*")
async def cancel_any_state(message: types.Message, state: FSMContext):
    """Универсальная отмена любого состояния"""
    current_state = await state.get_state()
    if current_state:
        data = await state.get_data()
        order_id = data.get('order_id')
        
        # Удаляем заказ если он есть
        if order_id and order_id in orders:
            del orders[order_id]
            
        await state.finish()
        await message.answer("❌ Операція скасована.", reply_markup=get_main_menu())
        logger.info(f"Пользователь {message.from_user.id} отменил состояние {current_state}")
    else:
        await message.answer("🏠 Ви в головному меню.", reply_markup=get_main_menu())

    
@dp.message_handler(lambda message: message.content_type != 'photo', 
                   state=CardPaymentStates.waiting_for_payment_screenshot)
async def handle_wrong_content_type(message: types.Message, state: FSMContext):
    await message.answer("❌ Будь ласка, надішліть скріншот оплати (фото), а не текст.")
    logger.warning(f"Пользователь {message.from_user.id} отправил неверный тип контента в состоянии ожидания скриншота")


# ДОБАВИТЬ этот обработчик в код:
@dp.message_handler(content_types=['photo'], state=CardPaymentStates.waiting_for_payment_screenshot)
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

@dp.message_handler(commands=['start'])
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

@dp.message_handler(commands=['help'])
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

@dp.message_handler(commands=['sendall'])
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
    
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            fail_count += 1
            logger.error(f"Помилка відправки користувачу {user_id}: {e}")
    
    await message.answer(f"📊 Розсилка завершена!\n✅ Успішно: {success_count}\n❌ Помилок: {fail_count}")
    logger.info(f"Рассылка завершена: успешно {success_count}, ошибок {fail_count}")

@dp.message_handler(commands=['stats'])
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

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для пользователя {user_id}: {e}")
        return False

@dp.callback_query_handler(lambda c: c.data == "check_subscription")
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

async def subscription_required(user_id: int) -> bool:
    if not await check_subscription(user_id):
        subscription_text = """❌ Щоб користуватися ботом, потрібно підписатися на наш основний канал!

📺 Підпишіться на канал і натисніть кнопку "Перевірити підписку" """
        
        await bot.send_message(
            user_id,
            subscription_text,
            reply_markup=get_subscription_keyboard()
        )
        logger.info(f"Пользователь {user_id} не подписан, отправлено сообщение о подписке")
        return False
    return True

@dp.message_handler(commands=['restart'])
async def restart_command(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає прав для використання цієї команди.")
        return
    
    await message.answer("🔄 Перезапускаю бота...")
    logger.info(f"Администратор {message.from_user.id} инициировал перезапуск")
    await safe_restart()

async def safe_restart():
    logger.info("🔄 Перезапуск бота через 3 секунды...")
    await asyncio.sleep(3)
    
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_message(admin_id, "🔄 Бот перезапускається через помилку...")
    except:
        pass
    
    os.execl(sys.executable, sys.executable, *sys.argv)

@dp.message_handler(Text(equals="🌟 Придбати зірки"))
async def stars_menu(message: types.Message):
    logger.info(f"Пользователь {message.from_user.id} запросил меню звезд")
    if not await subscription_required(message.from_user.id):
        logger.warning(f"Пользователь {message.from_user.id} не подписан на канал")
        return
        
    await message.answer(
        "🌟 Придбати зірки можна за такими цінами:",
        reply_markup=get_stars_menu()
    )

@dp.message_handler(Text(equals="💎 Придбати Telegram Premium"))
async def premium_menu(message: types.Message):
    if not await subscription_required(message.from_user.id):
        return
        
    await message.answer(
        "💎 Придбати Telegram Premium можна за такими цінами:",
        reply_markup=get_premium_menu()
    )

@dp.message_handler(Text(equals="📣 Канал з відгуками"))
async def reviews_channel(message: types.Message):
    if not await subscription_required(message.from_user.id):
        return
        
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📣 Перейти до каналу", url="https://t.me/starsZEMSTA"))
    await message.answer("📣 Перегляньте відгуки наших клієнтів у нашому каналі:", reply_markup=keyboard)
    logger.info(f"Пользователь {message.from_user.id} запросил канал с отзывами")

ADMIN_IDS = [6186532466,6862952576]

@dp.message_handler(Text(equals="🆘 Зв'язатися з підтримкою"))
async def support_contact(message: types.Message):
    if not await subscription_required(message.from_user.id):
        return
        
    keyboard = InlineKeyboardMarkup()
    random_admin_id = random.choice(ADMIN_IDS)
    keyboard.add(InlineKeyboardButton("💬 Написати підтримці", url=f"tg://user?id={random_admin_id}"))
    
    await message.answer("🆘 Для зв'язку з підтримкою натисніть кнопку нижче:", reply_markup=keyboard)
    logger.info(f"Користувач {message.from_user.id} запросив підтримку, обраний админ {random_admin_id}")

@dp.message_handler(Text(equals="📤 Розсилка"))
async def start_broadcast(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає прав для використання цієї команди.")
        logger.warning(f"Пользователь {message.from_user.id} попытался выполнить команду рассылки без прав администратора")
        return
    
    await message.answer("📝 Введіть текст для розсилки:")
    await BroadcastStates.waiting_for_broadcast_text.set()

@dp.callback_query_handler(lambda c: c.data == "back_to_main")
async def back_to_main_menu(callback_query: types.CallbackQuery):
    await callback_query.message.answer(
        "🔙 Повернення до головного меню:",
        reply_markup=get_main_menu()
    )
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} вернулся в главное меню")

@dp.callback_query_handler(lambda c: c.data.startswith("select_"))
async def handle_selection(callback_query: types.CallbackQuery, state: FSMContext):
    selection = callback_query.data.replace("select_", "")
    logger.info(f"Пользователь {callback_query.from_user.id} выбрал пакет: {selection}")
    if selection not in STAR_PRICES:
        logger.error(f"Пакет {selection} не найден для пользователя {callback_query.from_user.id}")
        await callback_query.answer("❌ Помилка: пакет не знайдено.")
        return
    
    order_data = STAR_PRICES[selection]
    
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
    
    payment_text = f"""💳 Выберите способ оплаты:

{'⭐ Кількість зірок: ' + str(order_data['stars']) if order_data['type'] == 'stars' else '💎 Термін: ' + str(order_data['months']) + ' місяців'}
💰 Сума до оплати: {order_data['price']}₴

Доступные способы оплаты:
💎 Оплата TON - через TON Connect
💳 Оплата картой"""
    
    logger.info(f"Отображение меню оплаты для заказа {order_id}")
    await callback_query.message.edit_text(payment_text, reply_markup=get_payment_method_keyboard(order_id))
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "cancel_order", state="*")
async def cancel_order_by_user(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('order_id')
    if order_id and order_id in orders:
        del orders[order_id]
        logger.info(f"Заказ {order_id} удален после отмены пользователем {callback_query.from_user.id}")
    await state.finish()
    await callback_query.message.edit_text("❌ Замовлення скасовано.")
    await callback_query.answer()
    logger.info(f"Пользователь {callback_query.from_user.id} отменил заказ")

@dp.message_handler(state=BroadcastStates.waiting_for_broadcast_text)
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
    
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            fail_count += 1
            logger.error(f"Помилка відправки користувачу {user_id}: {e}")
    
    await message.answer(f"📊 Розсилка завершена!\n✅ Успішно: {success_count}\n❌ Помилок: {fail_count}")
    logger.info(f"Рассылка завершена: успешно {success_count}, ошибок {fail_count}")
    await state.finish()

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

@dp.message_handler(lambda message: not message.text.startswith('/'), state=None, content_types=['text'])
async def handle_other_messages(message: types.Message):
    if not await subscription_required(message.from_user.id):
        return
        
    await message.answer("❓ Оберіть дію з меню нижче або введіть /help для довідки:", reply_markup=get_main_menu())
    logger.info(f"Пользователь {message.from_user.id} отправил неизвестное сообщение")

async def on_startup(dp):
    init_db()
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

if __name__ == '__main__':
    print("🌟 Telegram Bot для продажу зірок та Telegram Premium")
    print("🚀 Запуск бота...")
    print(f"👤 Адміністратор: {ADMIN_IDS}")
    print(f"🔗 API Split: {SPLIT_API_URL}")
    print(f"📺 Канал відгуків: {REVIEWS_CHANNEL_ID}")
    print(f"🔄 Авто-перезапуск: {'✅' if RESTART_ON_ERROR else '❌'}")
    print(f"💳 Номер картки: {CARD_NUMBER}")
    
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
