# Wumo Telegram Bot

[Русская версия](README.ru.md)

A small Telegram bot that fetches the daily [Wumo](https://wumo.com/) comic and can send it to subscribers on a schedule. It also serves any comic by date on request.

## Features

- Hourly scheduled check for a new comic; each subscriber gets at most one comic per day.
- `/today` — get today's comic immediately.
- Send a date as text (`03.03.2026`, `2026-03-03`, `3 March 2026`) to get that day's comic.
- `/toggle` — subscribe / unsubscribe.
- Referral links with per-user invitation counting.
- `/stats` — total users, active subscriptions and referral count (admin only).

## Requirements

- Python 3.10+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## Installation

```bash
git clone https://github.com/asitaka/wumo_bot.git
cd wumo_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```dotenv
BOT_TOKEN=123456789:AA...your-token-from-BotFather
ADMIN_ID=123456789
```

- `BOT_TOKEN` — required, the token issued by @BotFather.
- `ADMIN_ID` — optional, your Telegram user ID; enables `/stats`.

> Never commit `.env`. It is listed in `.gitignore`. If a token ever leaks, revoke it with @BotFather (`/mybots` → your bot → API Token → Revoke current token).

Run manually:

```bash
python bot.py
```

## Running as a systemd service

A typical unit (adjust paths and the user):

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

## Commands

| Command | Description |
|---|---|
| `/start` | Register and show the keyboard |
| `/status` | Show subscription status |
| `/toggle` | Subscribe or unsubscribe |
| `/today` | Get today's comic |
| `/share` | Get your referral link |
| `/help` | Show help |
| `/stats` | Admin-only statistics |

The reply keyboard has **Bot Status**, **Subscribe/Unsubscribe**, **Get Today's Comic** and **Share** buttons.

## Data and logs

Subscriber state is stored in `users_data.json` (gitignored), keyed by Telegram user ID:

| Field | Meaning |
|---|---|
| `is_active` | whether scheduled delivery is enabled |
| `last_sent_date` | date of the last successfully sent comic |
| `registration_date` | date of the first `/start` |
| `username` | Telegram username, captured on registration |
| `comics_received` | number of comics delivered |
| `last_manual_request` | timestamp of the last `/today` or date request |
| `referred_by` | ID of the user who invited this one |
| `referrals` | number of users invited by this user |

The bot logs to stdout/stderr only; systemd sends those to journald. Use `journalctl -u wumo-bot -f` to follow logs. File logging was intentionally removed, and the token is redacted from log records.
