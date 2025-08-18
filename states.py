from aiogram.dispatcher.filters.state import State, StatesGroup

class CardPaymentStates(StatesGroup):
    """Состояния для оплаты картой"""
    waiting_for_username = State()
    waiting_for_payment_screenshot = State()

class ReviewStates(StatesGroup):
    """Состояния для отзывов"""
    waiting_for_review_text = State()

class BroadcastStates(StatesGroup):
    """Состояния для рассылки"""
    waiting_for_broadcast_text = State()
