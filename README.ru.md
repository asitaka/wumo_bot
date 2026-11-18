# Wumo Telegram Bot

Небольшой Telegram-бот, который забирает ежедневный комикс [Wumo](https://wumo.com/) и может отправлять его подписчикам по расписанию. Также по запросу показывает любой комикс за конкретную дату.

[English version](README.md)

## Возможности

- Ежечасная проверка появления нового комикса; каждому подписчику отправляется не больше одного комикса в день.
- `/today` — получить сегодняшний комикс сразу.
- Если отправить дату текстом (`03.03.2026`, `2026-03-03`, `3 March 2026`), бот пришлёт комикс за этот день.
- `/toggle` — подписаться или отписаться.
- Реферальные ссылки с учётом приглашённых пользователей.
- `/stats` — общее число пользователей, активных подписок и приглашённых (только для админа).

## Требования

- Python 3.10+
- Токен Telegram-бота от [@BotFather](https://t.me/BotFather)

## Установка

```bash
git clone https://github.com/asitaka/wumo_bot.git
cd wumo_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Создайте файл `.env` в корне проекта:

```dotenv
BOT_TOKEN=123456789:AA...ваш-токен-от-BotFather
ADMIN_ID=123456789
```

- `BOT_TOKEN` — обязательно, токен, выданный @BotFather.
- `ADMIN_ID` — необязательно, ваш Telegram ID; включает команду `/stats`.

> Никогда не коммитьте `.env` — он добавлен в `.gitignore`. Если токен всё же утёк, отзовите его через @BotFather (`/mybots` → ваш бот → API Token → Revoke current token).

Запуск вручную:

```bash
python bot.py
```

## Запуск как systemd-сервис

Пример юнита (пути и пользователя поправьте под себя):

```ini
[Unit]
Description=Wumo Telegram Bot
After=network.target
Wants=network.target

[Service]
Type=simple
User=wumobot
Group=wumobot
WorkingDirectory=/opt/wumo_bot
Environment="PATH=/opt/wumo_bot/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONPATH=/opt/wumo_bot"
ExecStart=/opt/wumo_bot/venv/bin/python /opt/wumo_bot/bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=wumo-bot
UMask=0077

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wumo-bot
sudo journalctl -u wumo-bot -f
```

## Команды

| Команда | Описание |
|---|---|
| `/start` | Регистрация и показ клавиатуры |
| `/status` | Статус подписки |
| `/toggle` | Подписаться / отписаться |
| `/today` | Получить комикс за сегодня |
| `/share` | Получить свою реферальную ссылку |
| `/help` | Справка |
| `/stats` | Статистика, только для админа |

В клавиатуре кнопки **Bot Status**, **Subscribe/Unsubscribe**, **Get Today's Comic** и **Share**.

## Данные и логи

Состояние подписчиков хранится в `users_data.json` (в `.gitignore`), ключ — Telegram ID:

| Поле | Смысл |
|---|---|
| `is_active` | включена ли автоотправка |
| `last_sent_date` | дата последнего успешно отправленного комикса |
| `registration_date` | дата первого `/start` |
| `username` | Telegram-логин, сохранённый при регистрации |
| `comics_received` | количество полученных комиксов |
| `last_manual_request` | время последнего `/today` или запроса даты |
| `referred_by` | ID пользователя, который пригласил этого |
| `referrals` | количество приглашённых этим пользователем |

Бот пишет логи только в stdout/stderr, systemd направляет их в journald. Смотреть: `journalctl -u wumo-bot -f`. Файловое логирование намеренно убрано, а токен вырезается из записей лога.
