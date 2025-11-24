import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import telebot
from telebot import types
import os

# Конфигурация
BOT_TOKEN = "8490400287:AAHAw5scIAkm5fO7m-MINQ5VmM0k2aSYdk0"
TARGET_USER_ID = 472699161  # Замените на ID целевого пользователя

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rating_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('rating.db', check_same_thread=False)
    cursor = conn.cursor()

    # Таблица пользователей для хранения информации об изменяющих
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS users
                   (
                       user_id
                       INTEGER
                       PRIMARY
                       KEY,
                       username
                       TEXT,
                       first_name
                       TEXT,
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    # Таблица рейтинга (теперь только для целевого пользователя)
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS rating
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       current_rating
                       INTEGER
                       DEFAULT
                       0,
                       updated_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    # Таблица истории рейтинга
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS rating_history
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       change_amount
                       INTEGER,
                       changed_by
                       INTEGER,
                       reason
                       TEXT,
                       timestamp
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    # Таблица стандартных ачивок
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS standard_achievements
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       name
                       TEXT
                       UNIQUE,
                       description
                       TEXT,
                       condition_type
                       TEXT,
                       condition_value
                       INTEGER
                   )
                   ''')

    # Таблица пользовательских ачивок
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS custom_achievements
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       name
                       TEXT
                       UNIQUE,
                       description
                       TEXT,
                       impact
                       INTEGER,
                       created_by
                       INTEGER,
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    # Таблица полученных ачивок
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS user_achievements
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       achievement_id
                       INTEGER,
                       achievement_type
                       TEXT, -- 'standard' или 'custom'
                       granted_by
                       INTEGER,
                       granted_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP
                   )
                   ''')

    # Инициализируем начальный рейтинг, если его нет
    cursor.execute('SELECT COUNT(*) FROM rating')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO rating (current_rating) VALUES (0)')

    # Добавляем стандартные ачивки
    standard_achievements = [
        ("Первый шаг", "Первая оценка", "first_rating", 1),
        ("Новичок", "Рейтинг ≥10", "min_rating", 10),
        ("Мастер", "Рейтинг ≥50", "min_rating", 50),
        ("Падение", "Рейтинг ≤-10", "max_rating", -10),
        ("Клоун", "Попытка повысить свой рейтинг", "self_promotion", 1),
        ("Непопулярный", "Рейтинг ≤-20", "max_rating", -20),
        ("Настоящий инженер", "Рейтинг 500", "exact_rating", 500)
    ]

    cursor.executemany('''
                       INSERT
                       OR IGNORE INTO standard_achievements (name, description, condition_type, condition_value)
        VALUES (?, ?, ?, ?)
                       ''', standard_achievements)

    conn.commit()
    return conn


# Инициализация БД
db_connection = init_db()

# Система уровней
LEVELS = [
    (-500, -30, "📚 школяр"),
    (-29, -10, "🍺 баумановский бак"),
    (-9, -1, "🎓 баумановский маг"),
    (0, 9, "🥓 саловик"),
    (10, 19, "🔪 салорез"),
    (20, 39, "☕ кофемол"),
    (40, 69, "🧉 кофевар"),
    (70, 99, "🛠️ подсобный"),
    (100, 149, "🔄 главный по кнопкам"),
    (150, 199, "💼 поденщик"),
    (200, 249, "🐘 рабочий слон"),
    (250, 320, "📐 чертежник мечтатель"),
    (321, 399, "📄 мастер бумажного моделирования"),
    (400, 500, "⚡ ТЕХНОМАГ")
]


class RatingManager:
    def __init__(self, db_connection):
        self.db = db_connection

    def get_current_rating(self) -> int:
        """Получить текущий рейтинг целевого пользователя"""
        cursor = self.db.cursor()
        cursor.execute('SELECT current_rating FROM rating ORDER BY id DESC LIMIT 1')
        result = cursor.fetchone()
        return result[0] if result else 0

    def ensure_user_exists(self, user_id: int, username: str = "", first_name: str = ""):
        """Убедиться, что пользователь существует в базе"""
        cursor = self.db.cursor()
        cursor.execute(
            'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
            (user_id, username, first_name)
        )
        self.db.commit()

    def update_rating(self, changer_id: int, change_amount: int, reason: str = "") -> bool:
        """Обновить рейтинг целевого пользователя"""
        cursor = self.db.cursor()

        # Получаем текущий рейтинг
        current_rating = self.get_current_rating()
        new_rating = max(-500, min(500, current_rating + change_amount))

        # Обновляем рейтинг
        cursor.execute(
            'UPDATE rating SET current_rating = ?, updated_at = CURRENT_TIMESTAMP WHERE id = (SELECT id FROM rating ORDER BY id DESC LIMIT 1)',
            (new_rating,)
        )

        # Добавляем в историю
        cursor.execute(
            '''INSERT INTO rating_history (change_amount, changed_by, reason)
               VALUES (?, ?, ?)''',
            (change_amount, changer_id, reason)
        )

        self.db.commit()

        # Проверяем ачивки
        self.check_achievements(changer_id)

        return True

    def apply_achievement_impact(self, achievement_name: str, impact: int, granted_by: int) -> bool:
        """Применить влияние ачивки на рейтинг"""
        cursor = self.db.cursor()

        # Получаем текущий рейтинг
        current_rating = self.get_current_rating()
        new_rating = max(-500, min(500, current_rating + impact))

        # Обновляем рейтинг
        cursor.execute(
            'UPDATE rating SET current_rating = ?, updated_at = CURRENT_TIMESTAMP WHERE id = (SELECT id FROM rating ORDER BY id DESC LIMIT 1)',
            (new_rating,)
        )

        # Добавляем в историю
        reason = f"Ачивка: {achievement_name}"
        cursor.execute(
            '''INSERT INTO rating_history (change_amount, changed_by, reason)
               VALUES (?, ?, ?)''',
            (impact, granted_by, reason)
        )

        self.db.commit()

        # Проверяем ачивки после изменения рейтинга
        self.check_achievements(granted_by)

        return True

    def get_rating_history(self, limit: int = 10) -> List[Tuple]:
        """Получить историю изменений рейтинга"""
        cursor = self.db.cursor()
        cursor.execute('''
                       SELECT rh.change_amount, rh.reason, rh.timestamp, u.first_name
                       FROM rating_history rh
                                LEFT JOIN users u ON rh.changed_by = u.user_id
                       ORDER BY rh.timestamp DESC LIMIT ?
                       ''', (limit,))
        return cursor.fetchall()

    def get_level_info(self, rating: int) -> Tuple[str, int, int, float]:
        """Получить информацию об уровне"""
        for min_r, max_r, level_name in LEVELS:
            if min_r <= rating <= max_r:
                level_range = max_r - min_r
                progress = rating - min_r
                progress_percent = (progress / level_range) * 100 if level_range > 0 else 100
                return level_name, min_r, max_r, progress_percent
        return "Неизвестно", 0, 0, 0

    def create_progress_bar(self, percentage: float, length: int = 10) -> str:
        """Создать текстовый прогресс-бар"""
        filled = int(percentage / 100 * length)
        empty = length - filled
        return "█" * filled + "░" * empty

    def check_achievements(self, granted_by: int):
        """Проверить и выдать стандартные ачивки"""
        cursor = self.db.cursor()

        # Получаем текущий рейтинг
        rating = self.get_current_rating()

        # Получаем историю оценок
        cursor.execute('SELECT COUNT(*) FROM rating_history')
        rating_count = cursor.fetchone()[0]

        # Проверяем условия для стандартных ачивок
        conditions = [
            ("first_rating", 1, rating_count >= 1),
            ("min_rating", 10, rating >= 10),
            ("min_rating", 50, rating >= 50),
            ("max_rating", -10, rating <= -10),
            ("max_rating", -20, rating <= -20),
            ("exact_rating", 500, rating == 500)
        ]

        for condition_type, condition_value, condition_met in conditions:
            if condition_met:
                cursor.execute('''
                               SELECT id
                               FROM standard_achievements
                               WHERE condition_type = ?
                                 AND condition_value = ?
                               ''', (condition_type, condition_value))

                achievement = cursor.fetchone()
                if achievement:
                    achievement_id = achievement[0]

                    # Проверяем, есть ли уже эта ачивка
                    cursor.execute('''
                                   SELECT 1
                                   FROM user_achievements
                                   WHERE achievement_id = ?
                                     AND achievement_type = 'standard'
                                   ''', (achievement_id,))

                    if not cursor.fetchone():
                        # Выдаем ачивку
                        cursor.execute('''
                                       INSERT INTO user_achievements (achievement_id, achievement_type, granted_by)
                                       VALUES (?, 'standard', ?)
                                       ''', (achievement_id, granted_by))

        self.db.commit()

    def grant_clown_achievement(self, granted_by: int):
        """Выдать ачивку 'Клоун'"""
        cursor = self.db.cursor()

        cursor.execute('''
                       SELECT id
                       FROM standard_achievements
                       WHERE name = 'Клоун'
                       ''')

        achievement = cursor.fetchone()
        if achievement:
            achievement_id = achievement[0]

            # Проверяем, есть ли уже эта ачивка
            cursor.execute('''
                           SELECT 1
                           FROM user_achievements
                           WHERE achievement_id = ?
                             AND achievement_type = 'standard'
                           ''', (achievement_id,))

            if not cursor.fetchone():
                # Выдаем ачивку
                cursor.execute('''
                               INSERT INTO user_achievements (achievement_id, achievement_type, granted_by)
                               VALUES (?, 'standard', ?)
                               ''', (achievement_id, granted_by))

                self.db.commit()
                return True

        return False


# Инициализация менеджера рейтинга
rating_manager = RatingManager(db_connection)


def create_main_menu() -> types.ReplyKeyboardMarkup:
    """Создать главное меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("📈 Повысить", "📉 Понизить")
    keyboard.add("🐘 Наш слоняра", "🏆 Ачивки")
    keyboard.add("📊 История")
    return keyboard


def is_target_user(user_id: int) -> bool:
    """Проверить, является ли пользователь целевым"""
    return user_id == TARGET_USER_ID


@bot.message_handler(commands=['start'])
def handle_start(message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""

    # Убедимся, что пользователь есть в базе
    rating_manager.ensure_user_exists(user_id, username, first_name)

    welcome_text = (
        "🎉 Добро пожаловать в систему рейтинга!\n\n"
        "Здесь ты можешь управлять рейтингом нашего слоняры.\n\n"
        "Используй кнопки ниже для навигации:"
    )

    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=create_main_menu()
    )
    logger.info(f"User {user_id} started the bot")


@bot.message_handler(commands=['rating', 'level'])
def handle_rating(message):
    """Обработчик команды рейтинга"""
    rating = rating_manager.get_current_rating()
    level_name, min_r, max_r, progress_percent = rating_manager.get_level_info(rating)
    progress_bar = rating_manager.create_progress_bar(progress_percent)

    rating_text = (
        f"🐘 **Наш слоняра**\n\n"
        f"📊 **Рейтинг:** {rating}\n"
        f"🎯 **Уровень:** {level_name}\n"
        f"📈 **Прогресс:** {progress_percent:.1f}%\n"
        f"`{progress_bar}`\n"
        f"📏 **Диапазон:** {min_r} - {max_r}\n\n"
        f"*Следующий уровень при:* {max_r + 1 if rating < 500 else 'Максимум!'}"
    )

    bot.send_message(
        message.chat.id,
        rating_text,
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )


@bot.message_handler(commands=['levels'])
def handle_levels(message):
    """Показать все уровни"""
    levels_text = "🎯 **Система уровней:**\n\n"

    for min_r, max_r, level_name in LEVELS:
        levels_text += f"`{min_r:4d} - {max_r:4d}` - {level_name}\n"

    bot.send_message(
        message.chat.id,
        levels_text,
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )


@bot.message_handler(commands=['achievements'])
def handle_achievements(message):
    """Показать ачивки"""
    show_achievements(message)


def show_achievements(message):
    """Показать все полученные ачивки"""
    cursor = db_connection.cursor()

    # Получаем стандартные ачивки
    cursor.execute('''
                   SELECT sa.name, sa.description, ua.granted_at
                   FROM user_achievements ua
                            JOIN standard_achievements sa ON ua.achievement_id = sa.id
                   WHERE ua.achievement_type = 'standard'
                   ORDER BY ua.granted_at DESC
                   ''')

    standard_achievements = cursor.fetchall()

    # Получаем пользовательские ачивки
    cursor.execute('''
                   SELECT ca.name, ca.description, ca.impact, ua.granted_at
                   FROM user_achievements ua
                            JOIN custom_achievements ca ON ua.achievement_id = ca.id
                   WHERE ua.achievement_type = 'custom'
                   ORDER BY ua.granted_at DESC
                   ''')

    custom_achievements = cursor.fetchall()

    achievements_text = "🏆 **Ачивки слоняры:**\n\n"

    if not standard_achievements and not custom_achievements:
        achievements_text += "❌ Ачивок пока нет. Зарабатывайте рейтинг для получения ачивок!"
    else:
        if standard_achievements:
            achievements_text += "**Стандартные ачивки:**\n"
            for name, description, granted_at in standard_achievements:
                date = granted_at.split()[0] if granted_at else "Неизвестно"
                achievements_text += f"• {name} - {description} ({date})\n"
            achievements_text += "\n"

        if custom_achievements:
            achievements_text += "**Пользовательские ачивки:**\n"
            for name, description, impact, granted_at in custom_achievements:
                date = granted_at.split()[0] if granted_at else "Неизвестно"
                impact_sign = "+" if impact > 0 else ""
                achievements_text += f"• {name} - {description} ({impact_sign}{impact}) ({date})\n"

    bot.send_message(
        message.chat.id,
        achievements_text,
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )


@bot.message_handler(commands=['history'])
def handle_history(message):
    """Показать историю изменений"""
    show_history(message)


def show_history(message):
    """Показать историю изменений рейтинга"""
    try:
        history = rating_manager.get_rating_history()

        if not history:
            bot.send_message(
                message.chat.id,
                "📊 История изменений пуста.",
                reply_markup=create_main_menu()
            )
            return

        history_text = "📊 **Последние изменения рейтинга:**\n\n"

        for change_amount, reason, timestamp, changer_name in history:
            change_symbol = "➕" if change_amount > 0 else "➖"
            date = timestamp.split()[0] if timestamp else "Неизвестно"
            changer = changer_name or "Неизвестно"
            reason_text = f" - {reason}" if reason else ""

            history_text += f"`{change_symbol}{abs(change_amount):2d}` {date} от {changer}{reason_text}\n"

        bot.send_message(
            message.chat.id,
            history_text,
            parse_mode='Markdown',
            reply_markup=create_main_menu()
        )

    except Exception as e:
        logger.error(f"Error showing history: {e}")
        bot.send_message(
            message.chat.id,
            "❌ Произошла ошибка при получении истории. Попробуйте позже.",
            reply_markup=create_main_menu()
        )


@bot.message_handler(commands=['help'])
def handle_help(message):
    """Показать справку"""
    help_text = (
        "🤖 **Справка по боту рейтинга**\n\n"
        "**Основные команды:**\n"
        "• /start - начать работу\n"
        "• /help - справка по командам\n"
        "• /rating - текущий рейтинг\n"
        "• /achievements - ачивки\n"
        "• /history - история изменений\n"
        "• /status - статус бота\n\n"
        "**Команды администратора:**\n"
        "• /add - создать ачивку\n"
        "• /grant - выдать ачивку\n"
        "• /reset - сбросить данные\n\n"
        "**Кнопки меню:**\n"
        "• 📈 Повысить - +1 к рейтингу\n"
        "• 📉 Понизить - -1 к рейтингу\n"
        "• 🐘 Наш слоняра - информация о рейтинге\n"
        "• 🏆 Ачивки - список ачивок\n"
        "• 📊 История - история изменений"
    )

    bot.send_message(
        message.chat.id,
        help_text,
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )


@bot.message_handler(commands=['status'])
def handle_status(message):
    """Проверка статуса бота"""
    cursor = db_connection.cursor()
    cursor.execute('SELECT COUNT(*) FROM rating_history')
    history_count = cursor.fetchone()[0]

    current_rating = rating_manager.get_current_rating()

    status_text = (
        "✅ **Бот работает нормально**\n\n"
        f"📊 **Статистика:**\n"
        f"• Текущий рейтинг: {current_rating}\n"
        f"• Записей в истории: {history_count}\n"
        f"• Уровней в системе: {len(LEVELS)}\n"
        f"• Целевой пользователь: {'🟢 вы' if is_target_user(message.from_user.id) else '🔴 другой пользователь'}"
    )

    bot.send_message(
        message.chat.id,
        status_text,
        parse_mode='Markdown',
        reply_markup=create_main_menu()
    )


@bot.message_handler(func=lambda message: message.text == "📈 Повысить")
def handle_increase(message):
    """Обработчик повышения рейтинга"""
    if is_target_user(message.from_user.id):
        clown_text = (
            "🤡 *ЭТА КНОПКА НЕ ДЛЯ ТЕБЯ, АНДРЕЙ!*\n\n"
            "*Не пытайся повысить свой рейтинг!* 😠"
        )
        bot.send_message(
            message.chat.id,
            clown_text,
            parse_mode='Markdown',
            reply_markup=create_main_menu()
        )
        # Выдаем ачивку "Клоун"
        rating_manager.grant_clown_achievement(message.from_user.id)
        return

    # Убедимся, что пользователь есть в базе
    rating_manager.ensure_user_exists(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or ""
    )

    # Повышаем рейтинг целевого пользователя
    success = rating_manager.update_rating(
        message.from_user.id, 1, "Повышение рейтинга"
    )

    if success:
        new_rating = rating_manager.get_current_rating()
        bot.send_message(
            message.chat.id,
            f"✅ Рейтинг слоняры повышен на +1\n📊 Новый рейтинг: {new_rating}",
            reply_markup=create_main_menu()
        )


@bot.message_handler(func=lambda message: message.text == "📉 Понизить")
def handle_decrease(message):
    """Обработчик понижения рейтинга"""
    # Убедимся, что пользователь есть в базе
    rating_manager.ensure_user_exists(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or ""
    )

    # Понижаем рейтинг целевого пользователя
    success = rating_manager.update_rating(
        message.from_user.id, -1, "Понижение рейтинга"
    )

    if success:
        new_rating = rating_manager.get_current_rating()

        if is_target_user(message.from_user.id):
            response_text = (
                f"🎯 *Самобичевание прошло успешно!*\n\n"
                f"📊 Новый рейтинг: {new_rating}"
            )
        else:
            response_text = f"✅ Рейтинг слоняры понижен на -1\n📊 Новый рейтинг: {new_rating}"

        bot.send_message(
            message.chat.id,
            response_text,
            parse_mode='Markdown',
            reply_markup=create_main_menu()
        )


@bot.message_handler(func=lambda message: message.text == "🐘 Наш слоняра")
def handle_show_rating(message):
    """Показать рейтинг целевого пользователя"""
    handle_rating(message)


@bot.message_handler(func=lambda message: message.text == "🏆 Ачивки")
def handle_show_achievements(message):
    """Показать ачивки"""
    handle_achievements(message)


@bot.message_handler(func=lambda message: message.text == "📊 История")
def handle_show_history(message):
    """Показать историю"""
    show_history(message)


@bot.message_handler(commands=['add'])
def handle_add_achievement(message):
    """Создать новую ачивку"""
    if is_target_user(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "❌ У вас нет прав для создания ачивок!",
            reply_markup=create_main_menu()
        )
        return

    msg = bot.send_message(
        message.chat.id,
        "🎯 Создание новой ачивки. Введите название:",
        reply_markup=types.ForceReply(selective=True)
    )
    bot.register_next_step_handler(msg, process_achievement_name)


def process_achievement_name(message):
    """Обработка названия ачивки"""
    achievement_name = message.text
    msg = bot.send_message(
        message.chat.id,
        "📝 Введите описание ачивки:",
        reply_markup=types.ForceReply(selective=True)
    )
    bot.register_next_step_handler(msg, process_achievement_description, achievement_name)


def process_achievement_description(message, achievement_name):
    """Обработка описания ачивки"""
    achievement_description = message.text
    msg = bot.send_message(
        message.chat.id,
        "📊 Введите влияние ачивки на рейтинг (число, может быть отрицательным):",
        reply_markup=types.ForceReply(selective=True)
    )
    bot.register_next_step_handler(
        msg, process_achievement_impact,
        achievement_name, achievement_description
    )


def process_achievement_impact(message, achievement_name, achievement_description):
    """Обработка влияния ачивки и сохранение"""
    try:
        impact = int(message.text)

        cursor = db_connection.cursor()
        cursor.execute('''
                       INSERT INTO custom_achievements (name, description, impact, created_by)
                       VALUES (?, ?, ?, ?)
                       ''', (achievement_name, achievement_description, impact, message.from_user.id))

        db_connection.commit()

        bot.send_message(
            message.chat.id,
            f"✅ Ачивка '{achievement_name}' успешно создана!\n"
            f"📊 Влияние на рейтинг: {impact}",
            reply_markup=create_main_menu()
        )

    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ Неверный формат числа. Попробуйте снова.",
            reply_markup=create_main_menu()
        )
    except sqlite3.IntegrityError:
        bot.send_message(
            message.chat.id,
            "❌ Ачивка с таким названием уже существует.",
            reply_markup=create_main_menu()
        )


@bot.message_handler(commands=['grant'])
def handle_grant_achievement(message):
    """Выдать ачивку"""
    if is_target_user(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "❌ У вас нет прав для выдачи ачивок!",
            reply_markup=create_main_menu()
        )
        return

    # Получаем список пользовательских ачивок, которые еще не выданы
    cursor = db_connection.cursor()
    cursor.execute('''
                   SELECT ca.id, ca.name, ca.impact
                   FROM custom_achievements ca
                   WHERE ca.id NOT IN (SELECT ua.achievement_id
                                       FROM user_achievements ua
                                       WHERE ua.achievement_type = 'custom')
                   ''')

    available_achievements = cursor.fetchall()

    if not available_achievements:
        bot.send_message(
            message.chat.id,
            "❌ Нет доступных ачивок для выдачи. Все ачивки уже выданы или не созданы.",
            reply_markup=create_main_menu()
        )
        return

    # Создаем клавиатуру с доступными ачивками
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for achievement_id, name, impact in available_achievements:
        impact_sign = "+" if impact > 0 else ""
        keyboard.add(f"🎯 {name} ({impact_sign}{impact})")
    keyboard.add("❌ Отмена")

    msg = bot.send_message(
        message.chat.id,
        "🎯 Выберите ачивку для выдачи (в скобках указано влияние на рейтинг):",
        reply_markup=keyboard
    )
    bot.register_next_step_handler(msg, process_grant_achievement_choice, available_achievements)


def process_grant_achievement_choice(message, available_achievements):
    """Обработка выбора ачивки для выдачи"""
    if message.text == "❌ Отмена":
        bot.send_message(
            message.chat.id,
            "❌ Выдача ачивки отменена.",
            reply_markup=create_main_menu()
        )
        return

    # Извлекаем название ачивки из текста кнопки
    achievement_text = message.text.replace("🎯 ", "")
    achievement_name = achievement_text.split(" (")[0]  # Убираем часть с влиянием

    achievement_id = None
    achievement_impact = 0

    for aid, name, impact in available_achievements:
        if name == achievement_name:
            achievement_id = aid
            achievement_impact = impact
            break

    if not achievement_id:
        bot.send_message(
            message.chat.id,
            "❌ Ачивка не найдена или уже выдана.",
            reply_markup=create_main_menu()
        )
        return

    # Выдаем ачивку целевому пользователю
    cursor = db_connection.cursor()
    granted_by = message.from_user.id

    try:
        # Выдаем ачивку
        cursor.execute('''
                       INSERT INTO user_achievements (achievement_id, achievement_type, granted_by)
                       VALUES (?, 'custom', ?)
                       ''', (achievement_id, granted_by))

        # Применяем влияние ачивки на рейтинг
        rating_manager.apply_achievement_impact(achievement_name, achievement_impact, granted_by)

        db_connection.commit()

        new_rating = rating_manager.get_current_rating()
        impact_sign = "+" if achievement_impact > 0 else ""

        bot.send_message(
            message.chat.id,
            f"✅ Ачивка '{achievement_name}' успешно выдана слоняре!\n"
            f"📊 Влияние на рейтинг: {impact_sign}{achievement_impact}\n"
            f"🎯 Новый рейтинг: {new_rating}",
            reply_markup=create_main_menu()
        )

    except sqlite3.IntegrityError:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка: ачивка уже выдана.",
            reply_markup=create_main_menu()
        )


@bot.message_handler(commands=['reset'])
def handle_reset(message):
    """Сброс данных (только для администратора)"""
    if is_target_user(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "❌ У вас нет прав для сброса данных!",
            reply_markup=create_main_menu()
        )
        return

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("✅ Да, сбросить", callback_data="reset_confirm"))
    keyboard.add(types.InlineKeyboardButton("❌ Отмена", callback_data="reset_cancel"))

    bot.send_message(
        message.chat.id,
        "⚠️ **ВНИМАНИЕ!** Это действие сбросит ВСЕ данные:\n"
        "• Рейтинг слоняры\n"
        "• Историю изменений\n"
        "• Пользовательские ачивки\n"
        "• Выданные ачивки\n\n"
        "Вы уверены, что хотите продолжить?",
        parse_mode='Markdown',
        reply_markup=keyboard
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('reset_'))
def handle_reset_callback(call):
    """Обработчик callback для сброса данных"""
    if call.data == "reset_confirm":
        cursor = db_connection.cursor()

        # Сбрасываем все данные
        cursor.execute('DELETE FROM rating')
        cursor.execute('DELETE FROM rating_history')
        cursor.execute('DELETE FROM custom_achievements')
        cursor.execute('DELETE FROM user_achievements')
        cursor.execute('INSERT INTO rating (current_rating) VALUES (0)')
        cursor.execute('VACUUM')

        db_connection.commit()

        bot.edit_message_text(
            "✅ Все данные успешно сброшены!",
            call.message.chat.id,
            call.message.message_id
        )

    elif call.data == "reset_cancel":
        bot.edit_message_text(
            "❌ Сброс данных отменен.",
            call.message.chat.id,
            call.message.message_id
        )


@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    """Обработчик всех остальных сообщений"""
    if message.chat.type == 'private':  # Личные сообщения
        help_text = (
            "🤖 Я бот для управления рейтингом нашего слоняры!\n\n"
            "Используйте кнопки меню или команды:\n"
            "• /start - начать работу\n"
            "• /help - справка по командам\n"
            "• /rating - текущий рейтинг\n"
            "• /achievements - ачивки"
        )
        bot.send_message(
            message.chat.id,
            help_text,
            reply_markup=create_main_menu()
        )


def main():
    """Главная функция"""
    logger.info("Starting Rating Bot...")

    try:
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        # Перезапуск при сбое
        main()


if __name__ == "__main__":
    main()