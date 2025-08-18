import os
from dotenv import load_dotenv
import sqlite3
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Конфігурація з змінних оточення
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID_RAW = os.getenv('ADMIN_ID', '0')
ADMIN_IDS = [int(x.strip()) for x in ADMIN_ID_RAW.split(",") if x.strip()]
SPLIT_API_TOKEN = os.getenv('SPLIT_API_TOKEN')
SPLIT_API_URL = os.getenv('SPLIT_API_URL')
REVIEWS_CHANNEL_ID = int(os.getenv('REVIEWS_CHANNEL_ID', '0'))
RESTART_ON_ERROR = os.getenv('RESTART_ON_ERROR', 'true').lower() == 'true'
MAIN_CHANNEL_ID = int(os.getenv('MAIN_CHANNEL_ID', '0'))
CARD_NUMBER = os.getenv('CARD_NUMBER')
VIDEO_PATH = "payment_example.mp4"

# Ціни на зірки та Telegram Premium
STAR_PRICES = {
    "50⭐ – 42.5₴": {"stars": 50, "price": 42.5, "type": "stars"},
    "100⭐ – 85₴": {"stars": 100, "price": 85, "type": "stars"},
    "200⭐ – 170₴": {"stars": 200, "price": 170, "type": "stars"},
    "300⭐ – 255₴": {"stars": 300, "price": 255, "type": "stars"},
    "400⭐ – 340₴": {"stars": 400, "price": 340, "type": "stars"},
    "500⭐ – 390₴": {"stars": 500, "price": 390, "type": "stars"},
    "1000⭐ – 825₴": {"stars": 1000, "price": 825, "type": "stars"},
    "3 місяці💎 – 669₴": {"months": 3, "price": 669, "type": "premium"},
    "6 місяців💎 – 999₴": {"months": 6, "price": 999, "type": "premium"},
    "12 місяців💎 – 1699₴": {"months": 12, "price": 1699, "type": "premium"},
}

# Тимчасове зберігання замовлень
orders = {}

# Функция для загрузки пользователей из базы
def load_users():
    try:
        conn = sqlite3.connect('bot_database.db')
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        user_ids = {row[0] for row in c.fetchall()}
        conn.close()
        return user_ids
    except sqlite3.Error as e:
        logging.error(f"Ошибка при загрузке пользователей: {e}")
        return set()

# user_ids загружается из базы с обработкой ошибок
user_ids = load_users()
