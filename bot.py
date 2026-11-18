import json
import logging
import os
import re
import requests
from datetime import date, datetime
from urllib.parse import quote
from bs4 import BeautifulSoup
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

class TokenFilter(logging.Filter):
    """Вырезаем токен бота из всех сообщений лога."""
    def filter(self, record):
        token = globals().get("BOT_TOKEN")
        if token:
            record.msg = str(record.msg).replace(token, "***TOKEN***")
            args = record.args
            if isinstance(args, dict):
                record.args = {
                    k: v.replace(token, "***TOKEN***") if isinstance(v, str) else v
                    for k, v in args.items()
                }
            elif isinstance(args, tuple):
                record.args = tuple(
                    v.replace(token, "***TOKEN***") if isinstance(v, str) else v
                    for v in args
                )
        return True


_handler = logging.StreamHandler()
_handler.addFilter(TokenFilter())
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[_handler]
)
# httpx пишет полный URL запроса на INFO — в нём есть токен
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Загружаем переменные из .env
load_dotenv()

# Получаем токен из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    raise ValueError("❌ Ошибка: Токен бота не найден! Проверь .env файл.")

# Файл для хранения данных пользователей
DATA_FILE = "users_data.json"

# Определяем клавиатуру
keyboard = [
    ["Bot Status", "Subscribe/Unsubscribe"],
    ["Get Today's Comic", "Share"]
]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

# Заголовки для запросов (чтобы сайт не блокировал бота)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


# ==========================================================
# ФУНКЦИИ РАБОТЫ С ДАННЫМИ
# ==========================================================

def load_user_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def save_user_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# Глобальная переменная состояния (загружается при старте)
user_states = load_user_data()


# ==========================================================
# ФУНКЦИИ ПАРСИНГА И ДАТ
# ==========================================================

def parse_date_from_text(text):
    """
    Пытается извлечь дату из текста.
    Поддерживаемые форматы: DD.MM.YYYY, YYYY-MM-DD, 3 March 2026 и др.
    """
    text = text.strip()

    # 1. Числовые форматы (DD.MM.YYYY / DD/MM/YYYY / DD-MM-YYYY)
    match = re.match(r'^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$', text)
    if match:
        try:
            day, month, year = map(int, match.groups())
            date_obj = date(year, month, day)
            return validate_date(date_obj)
        except ValueError:
            return None, "❌ Incorrect date!"

    # 2. Числовые форматы (YYYY-MM-DD / YYYY.MM.DD)
    match = re.match(r'^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$', text)
    if match:
        try:
            year, month, day = map(int, match.groups())
            date_obj = date(year, month, day)
            return validate_date(date_obj)
        except ValueError:
            return None, "❌ Incorrect date!"

    # 3. Текстовые форматы (3 March 2026, 03 Mar 2026)
    for fmt in ['%d %B %Y', '%d %b %Y', '%B %d, %Y', '%b %d, %Y']:
        try:
            date_obj = datetime.strptime(text, fmt).date()
            return validate_date(date_obj)
        except ValueError:
            continue

    return None, (
        "❌ Unable to recognize date.\n"
        "Examples: 03.03.2026, 2026-03-03, 3 March 2026"
    )


def validate_date(date_obj):
    """Проверка на будущее и слишком старые даты"""
    if date_obj > date.today():
        return None, "❌ You can't request a comic from the future!"
    if date_obj < date(2010, 1, 1):
        return None, "❌ Date too old (available since 2010)."
    return date_obj, None


def check_page_status(year, month, day):
    """
    Проверяет наличие комикса за конкретную дату.
    Возвращает (True, [url]) или (False, []).
    """
    # Формируем URL БЕЗ лишних пробелов
    url = f"https://wumo.com/wumo/{year}/{month}/{day}"

    # Формируем строку даты КАК НА САЙТЕ (без ведущего нуля у дня): "3. March 2026"
    month_int = int(month)
    day_int = int(day)
    target_date_str = f"{day_int}. {date(year, month_int, day_int).strftime('%B %Y')}"

    print(f"🔍 Проверка: {url} | Ищем дату: {target_date_str}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)

        if response.status_code == 404:
            print("⚠️ Страница не найдена (404)")
            return False, []

        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')

            # СПОСОБ 1: Ищем основной article по точной дате
            # На сайте: <time>2. March 2026</time>
            time_tag = soup.find('time', string=target_date_str)

            if time_tag:
                article = time_tag.find_parent('article', class_='strip')
                if article:
                    img = article.find('img')
                    if img and img.get('src'):
                        img_url = img['src']
                        if not img_url.startswith('http'):
                            img_url = f"https://wumo.com{img_url}"
                        print(f"✅ Комикс найден (Способ 1): {img_url}")
                        return True, [img_url]

            # СПОСОБ 2: Ищем в секции LATEST WUMO
            latest_header = soup.find('h1', string='LATEST WUMO')
            if latest_header:
                container = latest_header.find_parent('div', class_='box-content')
                if container:
                    # Ищем все time в этой секции
                    for time_tag in container.find_all('time'):
                        if target_date_str in time_tag.text:
                            li = time_tag.find_parent('li')
                            if li:
                                img = li.find('img')
                                if img and img.get('src'):
                                    img_url = img['src']
                                    if not img_url.startswith('http'):
                                        img_url = f"https://wumo.com{img_url}"
                                    print(f"✅ Комикс найден (Способ 2): {img_url}")
                                    return True, [img_url]

            print("❌ Комикс не найден на странице")
            return False, []

    except Exception as e:
        logger.error(f"⚠️ Ошибка запроса: {e}", exc_info=True)
        return False, []


async def send_images(context, chat_id, img_urls):
    """Отправляет картинки пользователю, возвращает число успешно отправленных"""
    sent = 0
    for img_url in img_urls:
        try:
            # Убеждаемся, что URL полный
            if not img_url.startswith('http'):
                img_url = img_url.lstrip('/')
                img_url = f"https://wumo.com/{img_url}"

            await context.bot.send_photo(chat_id=chat_id, photo=img_url)
            sent += 1
        except Exception as e:
            logger.error(f"❌ Ошибка отправки фото: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed to load image: {img_url}")
    return sent


def record_comic_sent(user_id, manual=False):
    """Учитываем отправленный комикс и обновляем даты в users_data.json"""
    user_states = load_user_data()
    user = user_states.get(str(user_id))
    if user is None:
        return
    user['comics_received'] = user.get('comics_received', 0) + 1
    user['last_sent_date'] = str(date.today())
    if manual:
        user['last_manual_request'] = datetime.now().isoformat(timespec='seconds')
    save_user_data(user_states)


# ==========================================================
# ПЛАНИРОВЩИК (AUTO POST)
# ==========================================================

async def scheduled_check(context):
    """Периодическая проверка для подписчиков"""
    global user_states
    user_states = load_user_data()  # Перезагружаем на случай изменений

    today = str(date.today())
    user_id = str(context.job.chat_id)

    if user_id not in user_states:
        return

    user_data = user_states[user_id]

    # Если уже отправляли сегодня, пропускаем
    if user_data.get('last_sent_date') == today:
        return

    today_date = date.today()
    year = today_date.year
    month = f"{today_date.month:02d}"
    day = f"{today_date.day:02d}"

    exists, img_urls = check_page_status(year, month, day)

    if exists and img_urls:
        sent = await send_images(context, int(user_id), img_urls)
        if sent:
            record_comic_sent(user_id)


# ==========================================================
# ОБРАБОТЧИКИ КОМАНД
# ==========================================================

async def start(update: Update, context):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "No username"

    # Реферальная метка из ссылки вида /start ref_123456789
    ref_by = None
    if context.args and context.args[0].startswith("ref_"):
        candidate = context.args[0][4:]
        if candidate != user_id:
            ref_by = candidate

    if user_id not in user_states:
        user_states[user_id] = {
            'is_active': False,
            'last_sent_date': None,
            'registration_date': str(date.today()),
            'username': username,
            'comics_received': 0,
            'last_manual_request': None,
            'referred_by': ref_by,
            'referrals': 0
        }
        if ref_by and ref_by in user_states:
            user_states[ref_by]['referrals'] = user_states[ref_by].get('referrals', 0) + 1
        save_user_data(user_states)

    total_users = len(user_states)
    await update.message.reply_text(
        f"🤖 Bot is ready! Total users: {total_users}\n"
        "Use buttons or commands:\n"
        "/status - Check status\n"
        "/toggle - Subscribe/Unsubscribe\n"
        "/today - Get today's comic\n"
        "/help - Help\n"
        "\n📅 Or just send me a date (e.g., 03.03.2026)!",
        reply_markup=reply_markup
    )


async def check_status(update: Update, context):
    user_id = str(update.effective_user.id)
    user_data = user_states.get(user_id, {})
    status = "🟢 Active" if user_data.get('is_active') else "🔴 Inactive"

    await update.message.reply_text(
        f"📊 Subscription status:\n{status}",
        reply_markup=reply_markup
    )


async def toggle_subscription(update: Update, context):
    global user_states
    user_states = load_user_data()
    user_id = str(update.effective_user.id)

    user_data = user_states.setdefault(user_id, {
        'is_active': False,
        'last_sent_date': None,
        'registration_date': str(date.today()),
        'username': update.effective_user.username or "No username",
        'comics_received': 0,
        'last_manual_request': None
    })

    if user_data['is_active']:
        jobs = context.job_queue.get_jobs_by_name(f"check_{user_id}")
        for job in jobs:
            job.schedule_removal()
        user_data['is_active'] = False
        save_user_data(user_states)
        await update.message.reply_text("🛑 Subscription disabled", reply_markup=reply_markup)
    else:
        context.job_queue.run_repeating(
            scheduled_check, interval=3600, first=10, chat_id=int(user_id), name=f"check_{user_id}"
        )
        user_data['is_active'] = True
        save_user_data(user_states)
        await update.message.reply_text("✅ Subscription activated! First check in 10 seconds",
                                        reply_markup=reply_markup)


async def send_todays_comic(update: Update, context):
    """Обработчик кнопки и команды /today"""
    user_id = str(update.effective_user.id)
    today = date.today()
    year = today.year
    month = f"{today.month:02d}"
    day = f"{today.day:02d}"

    await update.message.reply_text("🔍 Checking for today's comic...", reply_markup=reply_markup)

    exists, img_urls = check_page_status(year, month, day)

    if exists and img_urls:
        sent = await send_images(context, update.effective_chat.id, img_urls)
        if sent:
            record_comic_sent(user_id, manual=True)
    else:
        await update.message.reply_text(
            "❌ Today's comic is not available yet.",
            reply_markup=reply_markup
        )


async def handle_date_message(update: Update, context):
    """Обрабатывает текстовые сообщения с датами"""
    text = update.message.text.strip()

    # Игнорируем команды (они обрабатываются отдельно)
    if text.startswith('/'):
        return

    date_obj, error = parse_date_from_text(text)

    if error:
        # Если это не похоже на дату, просто игнорируем или можно вывести подсказку
        # Сейчас выведем ошибку, чтобы пользователь понял, что бот ждет дату
        await update.message.reply_text(error, reply_markup=reply_markup)
        return

    date_str = date_obj.strftime("%d. %B %Y")
    await update.message.reply_text(f"🔍 Looking for a comic from {date_str}...", reply_markup=reply_markup)

    year = date_obj.year
    month = f"{date_obj.month:02d}"
    day = f"{date_obj.day:02d}"

    exists, img_urls = check_page_status(year, month, day)

    if exists and img_urls:
        sent = await send_images(context, update.effective_chat.id, img_urls)
        if sent:
            record_comic_sent(update.effective_user.id, manual=True)
    else:
        await update.message.reply_text(
            f"❌ Comic for {date_str} not found.\n"
            "It may not be published yet.",
            reply_markup=reply_markup
        )


async def help_command(update: Update, context):
    await update.message.reply_text(
        "🆘 Available commands:\n"
        "/start - Start bot\n"
        "/status - Check subscription status\n"
        "/toggle - Subscribe/Unsubscribe\n"
        "/today - Get today's comic immediately\n"
        "/share - Invite a friend\n"
        "/help - Show this message\n"
        "\n📅 You can also send me a date:\n"
        "03.03.2026 or 2026-03-03 or 3 March 2026",
        reply_markup=reply_markup
    )


async def share_command(update: Update, context):
    """Даёт реферальную ссылку и кнопку отправки в Telegram"""
    bot_username = context.bot.username
    if not bot_username:
        await update.message.reply_text("❌ Couldn't get the bot link.", reply_markup=reply_markup)
        return

    link = f"https://t.me/{bot_username}?start=ref_{update.effective_user.id}"
    share_url = (
        "https://t.me/share/url?url="
        + quote(link, safe='')
        + "&text="
        + quote("Your daily Wumo comic — subscribe 👇", safe='')
    )
    share_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Send to a friend", url=share_url)
    ]])
    await update.message.reply_text(
        f"🔗 Your link:\n{link}\n\n"
        "When a friend taps /start via this link, they'll be counted as your referral.",
        reply_markup=share_keyboard
    )


async def stats_command(update: Update, context):
    if ADMIN_ID and str(update.effective_user.id) == ADMIN_ID:
        total_users = len(user_states)
        active_users = sum(1 for user in user_states.values() if user.get('is_active'))
        referred_users = sum(1 for user in user_states.values() if user.get('referred_by'))
        await update.message.reply_text(
            f"📊 Bot Statistics:\n"
            f"Total users: {total_users}\n"
            f"Active subscriptions: {active_users}\n"
            f"Referred users: {referred_users}"
        )
    else:
        await update.message.reply_text("❌ Access denied.")


async def unknown_command(update: Update, context):
    await update.message.reply_text(
        "❌ Unknown command. Type /help to see available commands.",
        reply_markup=reply_markup
    )


# ==========================================================
# ЗАПУСК
# ==========================================================

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # Восстанавливаем активные подписки при перезапуске бота
    for user_id, user_data in user_states.items():
        if user_data.get('is_active'):
            application.job_queue.run_repeating(
                scheduled_check, interval=3600, first=10, chat_id=int(user_id), name=f"check_{user_id}"
            )

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", check_status))
    application.add_handler(CommandHandler("toggle", toggle_subscription))
    application.add_handler(CommandHandler("today", send_todays_comic))
    application.add_handler(CommandHandler("share", share_command))
    application.add_handler(CommandHandler("help", help_command))

    if ADMIN_ID:
        application.add_handler(CommandHandler("stats", stats_command))

    # Кнопки
    application.add_handler(MessageHandler(filters.Text("Bot Status"), check_status))
    application.add_handler(MessageHandler(filters.Text("Subscribe/Unsubscribe"), toggle_subscription))
    application.add_handler(MessageHandler(filters.Text("Get Today's Comic"), send_todays_comic))
    application.add_handler(MessageHandler(filters.Text("Share"), share_command))

    # 🆕 ОБРАБОТЧИК ДАТ (Важно: ДО unknown_command, но ПОСЛЕ кнопок)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date_message))

    # Неизвестные команды
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    print("✅ Bot is running...")
    application.run_polling()


if __name__ == '__main__':
    main()