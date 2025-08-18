from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMIN_IDS

def get_main_menu(user_id: int | None = None) -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("🌟 Придбати зірки"))
    keyboard.add(KeyboardButton("💎 Придбати Telegram Premium"))
    keyboard.add(KeyboardButton("🆘 Зв'язатися з підтримкою"))
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
        InlineKeyboardButton("500⭐ – 390₴", callback_data="select_500⭐ – 390₴"),
        InlineKeyboardButton("1000⭐ – 825₴", callback_data="select_1000⭐ – 825₴")
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

def get_ton_connect_keyboard(transaction_data: dict, recipient_address: str):
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