#!/usr/bin/env python3
\"\"\"
Webhook версия Telegram бота для Render
\"\"\"
import os
import asyncio
import logging
from aiohttp import web
from telegram_ai_bot import dp, bot

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка webhook
WEBHOOK_PATH = '/webhook'
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-app.onrender.com/webhook')

async def on_startup(app):
    \"\"\"Настройка webhook при запуске\"\"\"
    try:
        await bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f\" Webhook установлен: {WEBHOOK_URL}\")
    except Exception as e:
        logger.error(f\" Ошибка установки webhook: {e}\")

async def on_shutdown(app):
    \"\"\"Очистка webhook при остановке\"\"\"
    try:
        await bot.delete_webhook()
        logger.info(\" Webhook удален\")
    except Exception as e:
        logger.error(f\" Ошибка удаления webhook: {e}\")

async def health_check(request):
    \"\"\"Health check для Render\"\"\"
    return web.Response(text=\"Bot is running!\", status=200)

def main():
    \"\"\"Основная функция запуска\"\"\"
    logger.info(\" Запуск Telegram AI Bot (Webhook)\")
    
    # Проверка переменных окружения
    if not os.getenv('TELEGRAM_BOT_TOKEN'):
        logger.error(\" TELEGRAM_BOT_TOKEN не установлен\")
        return
    
    if not os.getenv('OPENROUTER_API_KEY'):
        logger.error(\" OPENROUTER_API_KEY не установлен\")
        return
    
    # Создание приложения
    app = web.Application()
    
    # Настройка маршрутов
    app.router.add_post(WEBHOOK_PATH, dp.webhook_handler())
    app.router.add_get('/', health_check)
    
    # Настройка событий
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    # Запуск сервера
    port = int(os.getenv('PORT', 8080))
    logger.info(f\" Сервер запускается на порту {port}\")
    
    web.run_app(app, port=port, host='0.0.0.0')

if __name__ == '__main__':
    main()
