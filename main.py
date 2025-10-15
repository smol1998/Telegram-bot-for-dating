import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import sqlite3
from math import radians, sin, cos, sqrt, atan2
from typing import Optional, Tuple, Dict, Any


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


ADMIN_USER_ID = 0000000  


def get_db_connection():
    conn = sqlite3.connect('dating.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row  
    return conn


def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            age INTEGER,
            bio TEXT,
            photo_file_id TEXT,
            latitude REAL,
            longitude REAL
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            liked_user_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(liked_user_id) REFERENCES users(id)
        )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            matched_user_id INTEGER,
            message TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(matched_user_id) REFERENCES users(id)
        )
        ''')
        conn.commit()


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0  
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])  
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance = R * c 
    return distance


async def send_location_to_admin(context: ContextTypes.DEFAULT_TYPE, user_id: int, latitude: float, longitude: float) -> None:
    try:
        await context.bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=f"Новый пользователь зарегистрирован! ID: {user_id}, Локация: https://www.google.com/maps?q={latitude},{longitude}"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления администратору: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()

   
    context.user_data['started'] = True

    if user:
        await update.message.reply_text(f"Привет, {user['name']}! Ты уже зарегистрирован.")
    else:
        await update.message.reply_text("Привет! Давай создадим твою анкету. Напиши свое имя:")


async def create_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    text = update.message.text

    if not context.user_data.get('started'):
        await update.message.reply_text("Пожалуйста, начните с команды /start.")
        return

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()

    if not user:
        await handle_profile_creation(update, context, text)
    else:
        await handle_user_interaction(update, context, text)

async def handle_profile_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if 'name' not in context.user_data:
        context.user_data['name'] = text
        await update.message.reply_text("Отлично! Теперь напиши свой возраст:")
    elif 'age' not in context.user_data:
        try:
            age = int(text)
            context.user_data['age'] = age
            await update.message.reply_text("Хорошо! Теперь напиши немного о себе:")
        except ValueError:
            await update.message.reply_text("Пожалуйста, введите корректный возраст.")
    elif 'bio' not in context.user_data:
        context.user_data['bio'] = text
        await update.message.reply_text("Отлично! Теперь отправь свою фотографию или видео:")

async def handle_user_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if text == "❤️" or text == "👎":
        await handle_like_dislike(update, context)
    elif text == "💤":
        await show_sleep_menu(update, context)
    elif text == "Старт💕":
        await search(update, context)
    elif text == "Моя анкета":
        await show_my_profile(update, context)
    elif text == "1. Смотреть анкеты":
        await search(update, context)
    elif text == "2. Моя анкета":
        await show_my_profile(update, context)
    elif text == "3. Настройки уведомлений":
        await update.message.reply_text("Вы выбрали настройки уведомлений. Этот функционал пока в разработке.")
    elif text == "4. Создать анкету":
        await create_profile(update, context)
    elif text == "1. Заполнить анкету заново":
        await reset_profile(update, context)
    elif text == "2. Изменить фото/видео":
        await update.message.reply_text("Пожалуйста, отправьте новое фото/видео.")
        context.user_data['editing_photo'] = True
    elif text == "3. Изменить текст анкеты":
        await update.message.reply_text("Пожалуйста, введите новый текст анкеты.")
        context.user_data['editing_bio'] = True
    elif text == "4. Назад":
        await show_sleep_menu(update, context)
    else:
        await handle_match_message(update, context)

async def reset_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        cursor.execute('DELETE FROM likes WHERE user_id = ? OR liked_user_id = ?', (user_id, user_id))
        cursor.execute('DELETE FROM messages WHERE user_id = ? OR matched_user_id = ?', (user_id, user_id))
        conn.commit()
    context.user_data.clear()
    await update.message.reply_text("Ваша анкета удалена. Давайте создадим новую анкету. Напишите свое имя:")


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type: str) -> None:
    user_id = update.message.from_user.id

    if not context.user_data.get('started'):
        await update.message.reply_text("Пожалуйста, начните с команды /start.")
        return

    if 'bio' not in context.user_data:
        await update.message.reply_text("Пожалуйста, сначала заполни текстовую информацию о себе.")
        return

    if 'editing_photo' in context.user_data and context.user_data['editing_photo']:
        await update_media(update, context, media_type)
    else:
        await save_new_profile(update, context, media_type)

async def update_media(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type: str) -> None:
    user_id = update.message.from_user.id
    media_file_id = update.message.photo[-1].file_id if media_type == 'photo' else update.message.video.file_id

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET photo_file_id = ? WHERE id = ?', (media_file_id, user_id))
        conn.commit()

    await update.message.reply_text("Фото/видео успешно обновлено!")
    context.user_data['editing_photo'] = False

async def save_new_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type: str) -> None:
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    media_file_id = update.message.photo[-1].file_id if media_type == 'photo' else update.message.video.file_id

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (id, username, name, age, bio, photo_file_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, context.user_data['name'], context.user_data['age'], context.user_data['bio'], media_file_id))
        conn.commit()

    location_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("Отправить местоположение", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text("Спасибо! Твоя анкета успешно создана. Теперь, пожалуйста, отправь свое местоположение:", reply_markup=location_keyboard)


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    location = update.message.location
    latitude = location.latitude
    longitude = location.longitude

    if not context.user_data.get('started'):
        await update.message.reply_text("Пожалуйста, начните с команды /start.")
        return

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT latitude, longitude FROM users WHERE id = ?', (user_id,))
        existing_location = cursor.fetchone()

        if existing_location and existing_location[0] is not None and existing_location[1] is not None:
            
            pass
        else:
            
            await send_location_to_admin(context, user_id, latitude, longitude)

        cursor.execute('UPDATE users SET latitude = ?, longitude = ? WHERE id = ?', (latitude, longitude, user_id))
        conn.commit()

    start_keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("Старт💕")],
            [KeyboardButton("Моя анкета")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text("Твое местоположение сохранено! Нажми кнопку 'Старт💕' для поиска анкет или 'Моя анкета' для просмотра и редактирования своей анкеты.", reply_markup=start_keyboard)


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id

    if not context.user_data.get('started'):
        await update.message.reply_text("Пожалуйста, начните с команды /start.")
        return

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id != ? AND id NOT IN (SELECT liked_user_id FROM likes WHERE user_id = ?) ORDER BY RANDOM() LIMIT 1', (user_id, user_id))
        profile = cursor.fetchone()

    if profile:
        await update.message.reply_text("Ищем анкеты...", reply_markup=ReplyKeyboardRemove())
        await show_next_profile(update, context, user_id)
    else:
        start_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("Старт💕")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text("Анкет больше нет. Нажмите 'Старт💕', чтобы проверить снова.", reply_markup=start_keyboard)


async def show_next_profile(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id != ? AND id NOT IN (SELECT liked_user_id FROM likes WHERE user_id = ?) ORDER BY RANDOM() LIMIT 1', (user_id, user_id))
        profile = cursor.fetchone()

    if profile:
        try:
            cursor.execute('SELECT latitude, longitude FROM users WHERE id = ?', (user_id,))
            current_user_location = cursor.fetchone()

            distance_text = "📍 Расстояние неизвестно"
            if current_user_location and current_user_location[0] and current_user_location[1]:
                distance = calculate_distance(
                    current_user_location[0], current_user_location[1],
                    profile['latitude'], profile['longitude']
                )
                distance_text = f"📍 {round(distance, 1)} км"

            keyboard = ReplyKeyboardMarkup(
                [[KeyboardButton("❤️"), KeyboardButton("👎"), KeyboardButton("💤")]],
                resize_keyboard=True,
                one_time_keyboard=True
            )

            if profile['photo_file_id'].startswith("AgAC"):
                await update.message.reply_photo(
                    profile['photo_file_id'],
                    caption=f"{profile['name']}, {profile['age']}\n{profile['bio']}\n{distance_text}",
                    reply_markup=keyboard
                )
            else:
                await update.message.reply_video(
                    profile['photo_file_id'],
                    caption=f"{profile['name']}, {profile['age']}\n{profile['bio']}\n{distance_text}",
                    reply_markup=keyboard
                )

            context.user_data['current_profile_id'] = profile['id']
        except Exception as e:
            logger.error(f"Ошибка при отправке медиа: {e}")
            await update.message.reply_text("Произошла ошибка при загрузке медиа. Попробуйте еще раз.")
    else:
        start_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("Старт💕")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await update.message.reply_text("Анкет больше нет. Нажмите 'Старт💕', чтобы проверить снова.", reply_markup=start_keyboard)


async def handle_like_dislike(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    text = update.message.text
    liked_user_id = context.user_data.get('current_profile_id')

    if liked_user_id:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if text == "❤️":
                cursor.execute('INSERT INTO likes (user_id, liked_user_id) VALUES (?, ?)', (user_id, liked_user_id))
                conn.commit()

                cursor.execute('SELECT * FROM likes WHERE user_id = ? AND liked_user_id = ?', (liked_user_id, user_id))
                mutual_like = cursor.fetchone()

                if mutual_like:
                    await handle_mutual_like(update, context, user_id, liked_user_id)
                else:
                    await update.message.reply_text("Лайк отправлен!")
                    await show_next_profile(update, context, user_id)

                try:
                    await context.bot.send_message(liked_user_id, "Кто-то лайкнул вашу анкету! Нажмите /search, чтобы узнать кто это😍.")
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления: {e}")

            elif text == "👎":
                await update.message.reply_text("Дизлайк отправлен!")
                await show_next_profile(update, context, user_id)
    else:
        await update.message.reply_text("Используйте команду /search для поиска анкет.")

async def handle_mutual_like(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, liked_user_id: int) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT username FROM users WHERE id = ?', (liked_user_id,))
        liked_user_username = cursor.fetchone()[0]
        cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
        current_user_username = cursor.fetchone()[0]

        user_link = f"https://t.me/{liked_user_username}" if liked_user_username else f"tg://user?id={liked_user_id}"
        current_user_link = f"https://t.me/{current_user_username}" if current_user_username else f"tg://user?id={user_id}"

        await update.message.reply_sticker(sticker="CAACAgUAAxkBAAIGUmeUGZkoFGnOIkwsbPkqK566XFeMAALpDQACyRUoVdu2RfDbVvPaNgQ")
        await update.message.reply_text(
            f'У вас взаимный лайк\\! [Нажмите здесь, чтобы написать]({user_link})',
            parse_mode='MarkdownV2'
        )

        try:
            await context.bot.send_sticker(
                chat_id=liked_user_id,
                sticker="CAACAgUAAxkBAAIGUmeUGZkoFGnOIkwsbPkqK566XFeMAALpDQACyRUoVdu2RfDbVvPaNgQ"
            )
            await context.bot.send_message(
                liked_user_id,
                f'У вас взаимный лайк\\! [Нажмите здесь, чтобы написать]({current_user_link})',
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")

        await search(update, context)


async def handle_match_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    text = update.message.text

    if 'matched_user_id' in context.user_data:
        matched_user_id = context.user_data['matched_user_id']
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO messages (user_id, matched_user_id, message) VALUES (?, ?, ?)', (user_id, matched_user_id, text))
            conn.commit()

        try:
            await context.bot.send_message(matched_user_id, f"Вам пришло сообщение от пользователя: {text}")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")

        await update.message.reply_text("Ваше сообщение отправлено!")
        del context.user_data['matched_user_id']
    else:
        await update.message.reply_text("Используйте команду /search для поиска анкет.")


async def show_sleep_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("1. Смотреть анкеты")],
            [KeyboardButton("2. Моя анкета")],
            [KeyboardButton("3. Настройки уведомлений")],
            [KeyboardButton("4. Создать анкету")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await update.message.reply_text("Выберите действие:", reply_markup=keyboard)


async def show_my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        profile = cursor.fetchone()

    if profile:
        keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton("1. Заполнить анкету заново")],
                [KeyboardButton("2. Изменить фото/видео")],
                [KeyboardButton("3. Изменить текст анкеты")],
                [KeyboardButton("4. Назад")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        if profile['photo_file_id'].startswith("AgAC"):
            await update.message.reply_photo(
                profile['photo_file_id'],
                caption=f"{profile['name']}, {profile['age']}\n{profile['bio']}",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_video(
                profile['photo_file_id'],
                caption=f"{profile['name']}, {profile['age']}\n{profile['bio']}",
                reply_markup=keyboard
            )
    else:
        await update.message.reply_text("Ваша анкета не найдена. Используйте команду /start для создания анкеты.")


def main() -> None:
    init_db()
    application = ApplicationBuilder().token("000000000000000000000000000000000000000000000000000").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("create_profile", create_profile))  # Оставляем, если нужно
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, lambda update, context: handle_media(update, context, 'photo')))
    application.add_handler(MessageHandler(filters.VIDEO, lambda update, context: handle_media(update, context, 'video')))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))

    application.run_polling()

if __name__ == '__main__':
    main()


pip install --upgrade apscheduler


pip install apscheduler==3.6.3


pip install pytz