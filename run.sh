#!/usr/bin/env bash
# Запуск LinkTree-бота: проверяет зависимости и запускает polling.
set -euo pipefail
cd "$(dirname "$0")"

if ! python3 -c "import aiogram, aiosqlite" 2>/dev/null; then
    echo "Ставлю зависимости..."
    python3 -m pip install --user -r requirements.txt
fi

if [ -z "${BOT_TOKEN:-}" ] && [ ! -f .env ]; then
    echo "Нет BOT_TOKEN: скопируй .env.example в .env и вставь токен от @BotFather"
    exit 1
fi

exec python3 bot.py
