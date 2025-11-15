import os
import telebot
from telebot import types
import sqlite3
import json
import logging
import time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получение токена из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)


# Инициализация базы данных
def init_db():
    """Инициализация базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS bot_data
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       key
                       TEXT
                       UNIQUE
                       NOT
                       NULL,
                       value
                       TEXT
                       NOT
                       NULL
                   )
                   ''')

    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS achievements
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       achievement_name
                       TEXT
                       UNIQUE
                       NOT
                       NULL,
                       achieved_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS rating_history
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       user_id
                       INTEGER
                       NOT
                       NULL,
                       user_name
                       TEXT
                       NOT
                       NULL,
                       change_amount
                       INTEGER
                       NOT
                       NULL,
                       new_rating
                       INTEGER
                       NOT
                       NULL,
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS chat_messages
                   (
                       chat_id
                       INTEGER
                       PRIMARY
                       KEY,
                       message_id
                       INTEGER
                       NOT
                       NULL,
                       updated_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    conn.commit()
    conn.close()


def get_db_connection():
    """Получение соединения с базой данных"""
    # На Heroku используем SQLite в постоянной директории
    database_path = '/app/rating_bot.db'
    return sqlite3.connect(database_path, check_same_thread=False)


def get_bot_data(key, default=None):
    """Получение данных из бота"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT value FROM bot_data WHERE key = ?', (key,))
    result = cursor.fetchone()

    conn.close()

    if result:
        return json.loads(result[0])
    return default


def set_bot_data(key, value):
    """Установка данных бота"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO bot_data (key, value) 
        VALUES (?, ?)
    ''', (key, json.dumps(value)))

    conn.commit()
    conn.close()


def add_rating_history(user_id, user_name, change_amount, new_rating):
    """Добавление записи в историю изменений рейтинга"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
                   INSERT INTO rating_history (user_id, user_name, change_amount, new_rating)
                   VALUES (?, ?, ?, ?)
                   ''', (user_id, user_name, change_amount, new_rating))

    conn.commit()
    conn.close()


def get_achievements():
    """Получение списка ачивок"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT achievement_name FROM achievements')
    results = cursor.fetchall()

    conn.close()

    return [result[0] for result in results]


def add_achievement(achievement_name):
    """Добавление ачивки"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
                       INSERT
                       OR IGNORE INTO achievements (achievement_name)
            VALUES (?)
                       ''', (achievement_name,))

        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False


def update_chat_message(chat_id, message_id):
    """Обновление ID сообщения бота для чата"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO chat_messages (chat_id, message_id)
        VALUES (?, ?)
    ''', (chat_id, message_id))

    conn.commit()
    conn.close()


def get_chat_message_id(chat_id):
    """Получение ID сообщения бота для чата"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT message_id FROM chat_messages WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()

    conn.close()

    return result[0] if result else None


# Инициализация данных при запуске
def init_bot_data():
    """Инициализация данных бота при первом запуске"""
    if get_bot_data('target_user_id') is None:
        set_bot_data('target_user_id', 472699161)  # ЗАМЕНИТЕ на реальный ID

    if get_bot_data('rating') is None:
        set_bot_data('rating', 0)


# Список доступных ачивок
available_achievements = [
    {"name": "Первый шаг", "description": "Получить первую оценку", "rating_effect": 5},
    {"name": "Новичок", "description": "Достигнуть рейтинга 10", "rating_effect": 10},
    {"name": "Мастер", "description": "Достигнуть рейтинга 50", "rating_effect": 20},
    {"name": "Падение", "description": "Упасть до рейтинга -10", "rating_effect": -5},
    {"name": "Клоун", "description": "Попытаться повысить себе рейтинг", "rating_effect": -10},
    {"name": "Звезда чата", "description": "Получить 10 изменений рейтинга в чате", "rating_effect": 15},
    {"name": "Непопулярный", "description": "Получить -10 изменений рейтинга в чате", "rating_effect": -10}
]


def create_main_keyboard():
    """Создает основную клавиатуру"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    btn_increase = types.InlineKeyboardButton("Повысить", callback_data="increase")
    btn_decrease = types.InlineKeyboardButton("Понизить", callback_data="decrease")
    btn_rating = types.InlineKeyboardButton("Наш слоняра", callback_data="show_rating")
    btn_achievements = types.InlineKeyboardButton("Список ачивок", callback_data="show_achievements")
    btn_history = types.InlineKeyboardButton("История", callback_data="show_history")

    keyboard.add(btn_increase, btn_decrease, btn_rating, btn_achievements, btn_history)

    return keyboard


def create_welcome_keyboard():
    """Создает клавиатуру для приветственного сообщения в чате"""
    keyboard = types.InlineKeyboardMarkup()
    btn_start = types.InlineKeyboardButton("Управлять рейтингом", callback_data="start_in_chat")
    keyboard.add(btn_start)
    return keyboard


def check_achievements():
    """Проверяет и добавляет новые ачивки"""
    rating = get_bot_data('rating', 0)
    current_achievements = get_achievements()

    for achievement in available_achievements:
        if achievement['name'] not in current_achievements:
            achieved = False

            if achievement['name'] == "Первый шаг" and len(current_achievements) == 0 and rating != 0:
                achieved = True
            elif achievement['name'] == "Новичок" and rating >= 10:
                achieved = True
            elif achievement['name'] == "Мастер" and rating >= 50:
                achieved = True
            elif achievement['name'] == "Падение" and rating <= -10:
                achieved = True

            if achieved:
                add_achievement(achievement['name'])
                new_rating = rating + achievement['rating_effect']
                set_bot_data('rating', new_rating)
                ensure_rating_limits()


def ensure_rating_limits():
    """Обеспечивает, чтобы рейтинг оставался в пределах -500 до 500"""
    rating = get_bot_data('rating', 0)
    if rating > 500:
        set_bot_data('rating', 500)
    elif rating < -500:
        set_bot_data('rating', -500)


@bot.message_handler(commands=['start'])
def start_command(message):
    """Обработчик команды /start"""
    welcome_text = (
        "Привет! Я бот для управления рейтингом нашего слоняры.\n\n"
        "Используй кнопки ниже для взаимодействия:"
    )
    msg = bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=create_main_keyboard()
    )

    if message.chat.type in ['group', 'supergroup']:
        update_chat_message(message.chat.id, msg.message_id)


@bot.message_handler(commands=['rating'])
def rating_command(message):
    """Команда для быстрого просмотра рейтинга"""
    rating = get_bot_data('rating', 0)
    emoji = "🐘" if rating > 0 else "🐍" if rating < 0 else "🦒"

    rating_text = f"{emoji} Текущий рейтинг нашего слоняры: {rating}"
    bot.send_message(message.chat.id, rating_text)


@bot.message_handler(commands=['achievements'])
def achievements_command(message):
    """Команда для просмотра ачивок"""
    achievements_list = get_achievements()

    if not achievements_list:
        achievements_text = "📋 Пока никаких ачивок нет. Продолжайте в том же духе!"
    else:
        achievements_text = "🏆 Список ачивок:\n\n"
        for i, achievement_name in enumerate(achievements_list, 1):
            achievement_data = next((a for a in available_achievements if a['name'] == achievement_name), None)
            if achievement_data:
                effect = achievement_data['rating_effect']
                effect_symbol = "+" if effect > 0 else ""
                achievements_text += f"{i}. {achievement_data['name']}\n"
                achievements_text += f"   📝 {achievement_data['description']}\n"
                achievements_text += f"   ⭐ Влияние на рейтинг: {effect_symbol}{effect}\n\n"

    bot.send_message(message.chat.id, achievements_text)


@bot.message_handler(commands=['history'])
def history_command(message):
    """Команда для просмотра истории изменений"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
                   SELECT user_name, change_amount, new_rating, created_at
                   FROM rating_history
                   ORDER BY created_at DESC LIMIT 10
                   ''')

    history_records = cursor.fetchall()
    conn.close()

    if not history_records:
        history_text = "📊 История изменений пуста."
    else:
        history_text = "📊 Последние 10 изменений рейтинга:\n\n"
        for record in reversed(history_records):
            user_name, change_amount, new_rating, created_at = record
            change_emoji = "📈" if change_amount > 0 else "📉"
            change_symbol = "+" if change_amount > 0 else ""
            history_text += f"{change_emoji} {user_name}: {change_symbol}{change_amount}\n"
            history_text += f"   🎯 Новый рейтинг: {new_rating}\n"
            history_text += f"   ⏰ {created_at[:16]}\n\n"

    bot.send_message(message.chat.id, history_text)


@bot.message_handler(commands=['reset'])
def reset_command(message):
    """Команда для сброса данных (только для администратора)"""
    if message.from_user.id != get_bot_data('target_user_id'):
        set_bot_data('rating', 0)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM achievements')
        cursor.execute('DELETE FROM rating_history')
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, "♻️ Все данные сброшены!")
    else:
        bot.send_message(message.chat.id, "❌ У вас нет прав для этой команды.")


@bot.message_handler(commands=['status'])
def status_command(message):
    """Команда для проверки статуса бота"""
    bot.send_message(message.chat.id, "✅ Бот работает исправно!")


@bot.message_handler(content_types=['new_chat_members'])
def new_chat_member(message):
    """Обработчик добавления бота в чат"""
    for user in message.new_chat_members:
        if user.id == bot.get_me().id:
            welcome_text = (
                "Привет всем! 🐘\n"
                "Я бот для управления рейтингом нашего слоняры.\n\n"
                "Теперь вы можете управлять рейтингом прямо здесь!\n"
                "Используйте команды:\n"
                "/start - открыть панель управления\n"
                "/rating - посмотреть текущий рейтинг\n"
                "/achievements - список ачивок\n"
                "/history - история изменений\n"
                "/status - проверить работу бота\n\n"
                "Или нажмите кнопку ниже:"
            )
            msg = bot.send_message(
                message.chat.id,
                welcome_text,
                reply_markup=create_welcome_keyboard()
            )
            update_chat_message(message.chat.id, msg.message_id)


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """Обработчик нажатий на кнопки"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    user_name = call.from_user.first_name or "Неизвестный"

    if call.data == "start_in_chat":
        welcome_text = "🐘 Панель управления рейтингом слоняры\n\nИспользуйте кнопки ниже:"
        try:
            msg = bot.send_message(chat_id, welcome_text, reply_markup=create_main_keyboard())
            update_chat_message(chat_id, msg.message_id)
            bot.answer_callback_query(call.id, "Панель управления открыта!")
        except:
            bot.answer_callback_query(call.id, "Ошибка отправки сообщения")
        return

    elif call.data == "increase":
        target_user_id = get_bot_data('target_user_id')
        current_rating = get_bot_data('rating', 0)

        if user_id == target_user_id:
            clown_achievement = next((a for a in available_achievements if a['name'] == "Клоун"), None)
            if clown_achievement and clown_achievement['name'] not in get_achievements():
                add_achievement(clown_achievement['name'])
                new_rating = current_rating + clown_achievement['rating_effect']
                set_bot_data('rating', new_rating)
                ensure_rating_limits()

            bot.answer_callback_query(call.id, "🤡 Эта кнопка не для тебя, Андрей.", show_alert=True)
        else:
            new_rating = current_rating + 1
            set_bot_data('rating', new_rating)
            ensure_rating_limits()
            check_achievements()

            add_rating_history(user_id, user_name, 1, new_rating)
            bot.send_message(chat_id, f"📈 {user_name} повысил рейтинг слоняры! Новый рейтинг: {new_rating}")
            bot.answer_callback_query(call.id, "Рейтинг повышен на 1!")

    elif call.data == "decrease":
        current_rating = get_bot_data('rating', 0)
        new_rating = current_rating - 1
        set_bot_data('rating', new_rating)
        ensure_rating_limits()
        check_achievements()

        add_rating_history(user_id, user_name, -1, new_rating)
        action = "понизил" if user_id != get_bot_data('target_user_id') else "самопонизился"
        bot.send_message(chat_id, f"📉 {user_name} {action} рейтинг слоняры! Новый рейтинг: {new_rating}")
        bot.answer_callback_query(call.id, "Рейтинг понижен на 1!")

    elif call.data == "show_rating":
        rating = get_bot_data('rating', 0)
        emoji = "🐘" if rating > 0 else "🐍" if rating < 0 else "🦒"
        rating_text = f"{emoji} Текущий рейтинг нашего слоняры: {rating}"
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, rating_text)
        return

    elif call.data == "show_achievements":
        achievements_list = get_achievements()

        if not achievements_list:
            achievements_text = "📋 Пока никаких ачивок нет. Продолжайте в том же духе!"
        else:
            achievements_text = "🏆 Список ачивок:\n\n"
            for i, achievement_name in enumerate(achievements_list, 1):
                achievement_data = next((a for a in available_achievements if a['name'] == achievement_name), None)
                if achievement_data:
                    effect = achievement_data['rating_effect']
                    effect_symbol = "+" if effect > 0 else ""
                    achievements_text += f"{i}. {achievement_data['name']}\n"
                    achievements_text += f"   📝 {achievement_data['description']}\n"
                    achievements_text += f"   ⭐ Влияние на рейтинг: {effect_symbol}{effect}\n\n"

        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, achievements_text)
        return

    elif call.data == "show_history":
        # Создаем временное сообщение для вызова history_command
        temp_msg = type('MockMessage', (), {'chat': type('MockChat', (), {'id': chat_id})})()
        history_command(temp_msg)
        bot.answer_callback_query(call.id)
        return

    # Обновляем сообщение с клавиатурой
    try:
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=create_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка обновления клавиатуры: {e}")
        try:
            welcome_text = "🐘 Панель управления рейтингом слоняры\n\nИспользуйте кнопки ниже:"
            msg = bot.send_message(chat_id, welcome_text, reply_markup=create_main_keyboard())
            update_chat_message(chat_id, msg.message_id)
        except:
            pass


@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text_messages(message):
    """Обработчик текстовых сообщений"""
    if message.chat.type in ['group', 'supergroup']:
        text_lower = message.text.lower()
        if 'рейтинг' in text_lower and 'слон' in text_lower:
            rating = get_bot_data('rating', 0)
            emoji = "🐘" if rating > 0 else "🐍" if rating < 0 else "🦒"
            rating_text = f"{emoji} Текущий рейтинг нашего слоняры: {rating}"
            bot.reply_to(message, rating_text)


# Инициализация при запуске
"""init_db()
init_bot_data()
logger.info("База данных инициализирована")"""

# Запуск бота с обработкой ошибок


if __name__ == "__main__":
    logger.info("Запуск бота...")
    init_db()
    init_bot_data()

    while True:
        try:
            logger.info("Бот запущен и работает")
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            logger.info("Перезапуск через 10 секунд...")
            time.sleep(10)