import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

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
        c.execute("SELECT COUNT(*) FROM reviews WHERE id >= 60")
        conflict_count = c.fetchone()[0]
        if conflict_count == 0:  # Если нет конфликтующих записей
            # Установка начального значения автоинкремента на 59 (следующий ID будет 60)
            c.execute("SELECT seq FROM sqlite_sequence WHERE name='reviews'")
            result = c.fetchone()
            if result is None:
                c.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('reviews', 59)")
                logger.info("Автоинкремент для reviews установлен на 59 (следующий ID будет 60)")
            elif result[0] < 59:
                c.execute("UPDATE sqlite_sequence SET seq = 59 WHERE name = 'reviews'")
                logger.info("Автоинкремент для reviews обновлен на 59 (следующий ID будет 60)")
        else:
            # Если есть отзывы с id >= 60, логируем текущий seq
            c.execute("SELECT seq FROM sqlite_sequence WHERE name='reviews'")
            result = c.fetchone()
            current_seq = result[0] if result else 0
            logger.info(f"Найдены отзывы с id >= 60, текущий seq = {current_seq}, следующий ID будет {current_seq + 1}")

        conn.commit()
        logger.info("База данных успешно инициализирована")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
    finally:
        conn.close()

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




        