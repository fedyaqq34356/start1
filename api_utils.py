import aiohttp
import logging
from typing import Optional, Dict

from config import SPLIT_API_TOKEN, SPLIT_API_URL

logger = logging.getLogger(__name__)

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







        