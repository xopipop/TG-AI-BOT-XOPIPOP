#!/usr/bin/env python3
"""
Webhook версия Telegram бота для Render
Обновлено: 2025-08-06 - Исправлен API для aiogram 3.x
"""
import os
import logging
import asyncio
from aiohttp import web
from telegram_ai_bot import dp, bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-app.onrender.com/webhook")

async def health_check(request):
    return web.Response(text="Bot is running!", status=200)

async def webhook_handler(request):
    """Обработчик webhook для aiogram 3.x"""
    try:
        update = await request.json()
        await dp.feed_update(bot, update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return web.Response(status=500)

async def on_startup(app):
    """Действия при запуске приложения"""
    logger.info("🚀 Настройка webhook...")
    try:
        await bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")

async def on_shutdown(app):
    """Действия при остановке приложения"""
    logger.info("🛑 Удаление webhook...")
    try:
        await bot.delete_webhook()
        logger.info("✅ Webhook удален")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления webhook: {e}")
    
    # Закрываем сессии aiohttp
    logger.info("🛑 Закрытие сессий...")
    try:
        await bot.session.close()
        logger.info("✅ Сессии закрыты")
    except Exception as e:
        logger.error(f"❌ Ошибка закрытия сессий: {e}")

def main():
    logger.info("🚀 Запуск Telegram AI Bot (Webhook) - v2.0")
    app = web.Application()
    
    # Добавляем обработчики
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    app.router.add_get("/", health_check)
    
    # Добавляем события запуска и остановки
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, port=port, host="0.0.0.0")

if __name__ == "__main__":
    main()
