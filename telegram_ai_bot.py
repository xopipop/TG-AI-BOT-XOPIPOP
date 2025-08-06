#!/usr/bin/env python3
"""
Telegram AI Bot - Умный бот с поддержкой современных AI моделей
Поддерживает анализ текста, документов, изображений с OCR
"""

import asyncio
import logging
import os
import json
import aiohttp
import aiofiles
import sys
import subprocess
import platform
import urllib.request
from pathlib import Path
from functools import lru_cache
from typing import Optional, Tuple, List
import re

# Загрузка переменных окружения из файла .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv не установлен, используем системные переменные окружения

# Условные импорты с ленивой загрузкой
try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    Image = None
    TESSERACT_AVAILABLE = False

try:
    from PyPDF2 import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PdfReader = None
    PDF_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    Document = None
    DOCX_AVAILABLE = False

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# --- КОНФИГУРАЦИЯ ---
# Безопасное получение токенов из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Проверка наличия токенов
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Пожалуйста, установите переменную окружения TELEGRAM_BOT_TOKEN в файле .env")

if not OPENROUTER_API_KEY:
    raise ValueError("Пожалуйста, установите переменную окружения OPENROUTER_API_KEY в файле .env")

# --- КОНЕЦ КОНФИГУРАЦИИ ---

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# User preferences storage (in-memory, resets on restart)
user_prefs = {}

# История сообщений для каждого пользователя (память диалога)
user_chat_history = {}

# Кэш для файлов (LRU cache)
import weakref

# Кэш обработанных файлов 
_file_cache = {}

# Лимиты файлов
MAX_FILE_SIZE_MB = 20
MAX_PDF_PAGES = 50
MAX_TEXT_LENGTH = 10000

# Лимиты памяти диалога
MAX_CHAT_HISTORY = 20  # Максимальное количество сообщений в истории
MAX_CONTEXT_TOKENS = 8000  # Приблизительный лимит токенов контекста

# Доступные AI модели
AVAILABLE_MODELS = {
    "auto": "🤖 Авто (умный выбор)",
    "openai/gpt-oss-120b": "🆕 GPT-OSS-120B",
    "openai/gpt-oss-20b": "🔹 GPT-OSS-20B",
    "deepseek/deepseek-r1-0528:free": "🧠 DeepSeek R1 (бесплатно)",
    "qwen/qwen3-235b-a22b:free": "🚀 Qwen3-235B (бесплатно)",
    "qwen/qwen-2.5-coder-32b-instruct:free": "💻 Qwen Coder (бесплатно)",
    "moonshotai/kimi-k2": "🌙 Kimi K2",
    "anthropic/claude-sonnet-4": "📖 Claude Sonnet 4",
    "google/gemini-2.5-pro": "💎 Gemini 2.5 Pro"
}

# Модели с поддержкой изображений (мультимодальные)
VISION_MODELS = {
    "google/gemini-2.5-pro",
    "anthropic/claude-sonnet-4",
    "openai/gpt-oss-120b",
    "moonshotai/kimi-k2"
}

# Конфигурация
DOWNLOADS_DIR = Path("downloads")
TESSERACT_DIR = Path("tesseract")
CONFIG_DIR = Path("config")

# Создаем папки
DOWNLOADS_DIR.mkdir(exist_ok=True)
TESSERACT_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)

# Кэш для проверки Tesseract
_tesseract_cache = None

def get_main_keyboard():
    """Создает основную клавиатуру с настройками"""
    builder = ReplyKeyboardBuilder()
    
    # Основные функции
    builder.row(
        KeyboardButton(text="🤖 Выбор модели"),
        KeyboardButton(text="📊 Статус")
    )
    builder.row(
        KeyboardButton(text="💭 Память диалога"),
        KeyboardButton(text="ℹ️ Помощь")
    )
    builder.row(
        KeyboardButton(text="🗑️ Очистить чат")
    )
    
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)

def get_model_keyboard():
    """Создает клавиатуру для выбора модели"""
    builder = ReplyKeyboardBuilder()
    
    # Добавляем кнопки для каждой модели
    for model_id, model_name in AVAILABLE_MODELS.items():
        builder.row(KeyboardButton(text=model_name))
    
    builder.row(KeyboardButton(text="🔙 Назад"))
    
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=False)





def add_to_chat_history(user_id: int, role: str, content: str):
    """Добавляет сообщение в историю чата пользователя"""
    if user_id not in user_chat_history:
        user_chat_history[user_id] = []
    
    user_chat_history[user_id].append({
        "role": role,
        "content": content,
        "timestamp": asyncio.get_event_loop().time()
    })
    
    # Ограничиваем размер истории
    if len(user_chat_history[user_id]) > MAX_CHAT_HISTORY:
        user_chat_history[user_id] = user_chat_history[user_id][-MAX_CHAT_HISTORY:]

def get_chat_context(user_id: int, include_system: bool = True) -> list:
    """Получает контекст чата для пользователя в формате OpenAI API"""
    messages = []
    
    if include_system:
        messages.append({
            "role": "system",
            "content": """Отвечай коротко и лаконично, как это принято в чатах, используй эмоджи где это уместно.
            Строго не используй разметку Markdown!
            Ты полезный помощник в Telegram. 
            Пользователь может присылать текст, документы или изображения.
            Если пользователь прислал файл, ты получишь информацию о его содержимом.
            Если файл содержит текст, ты можешь его анализировать и отвечать на вопросы.
            Если это изображение, ты можешь описать его содержимое если есть OCR данные.
            Отвечай коротко и ясно, используй эмодзи где уместно.
            
            ВАЖНО: Ты ведешь продолжительный диалог с пользователем. Помни предыдущие сообщения и отвечай в контексте разговора."""
        })
    
    # Добавляем историю сообщений пользователя
    if user_id in user_chat_history:
        for msg in user_chat_history[user_id]:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
    
    return messages

def clear_chat_history(user_id: int):
    """Очищает историю чата пользователя"""
    if user_id in user_chat_history:
        del user_chat_history[user_id]

def estimate_tokens(text: str) -> int:
    """Приблизительная оценка количества токенов в тексте"""
    # Примерная оценка: 1 токен ≈ 4 символа для английского, 6 для русского
    return len(text) // 5

def trim_context_if_needed(messages: list) -> list:
    """Обрезает контекст если он слишком большой"""
    total_tokens = sum(estimate_tokens(msg["content"]) for msg in messages)
    
    if total_tokens <= MAX_CONTEXT_TOKENS:
        return messages
    
    # Сохраняем системное сообщение и обрезаем старые сообщения
    system_msg = messages[0] if messages and messages[0]["role"] == "system" else None
    user_messages = messages[1:] if system_msg else messages
    
    # Обрезаем старые сообщения, оставляя последние
    while user_messages and estimate_tokens("".join(msg["content"] for msg in user_messages)) > MAX_CONTEXT_TOKENS - 500:
        user_messages.pop(0)
    
    result = []
    if system_msg:
        result.append(system_msg)
    result.extend(user_messages)
    
    return result

@lru_cache(maxsize=1)
def check_tesseract_installation() -> Tuple[bool, str]:
    """Проверяет установку Tesseract OCR с кэшированием"""
    global _tesseract_cache
    
    if _tesseract_cache is not None:
        return _tesseract_cache
    
    try:
        if not TESSERACT_AVAILABLE:
            _tesseract_cache = (False, "Модуль pytesseract не установлен")
            return _tesseract_cache
        
        # Читаем сохраненный путь
        config_file = CONFIG_DIR / 'tesseract_path.txt'
        possible_paths = []
        
        if config_file.exists():
            try:
                saved_path = config_file.read_text().strip()
                if saved_path and Path(saved_path).exists():
                    possible_paths.append(saved_path)
            except:
                pass
        
        # Стандартные пути
        standard_paths = [
            r"C:\Users\User-01\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files\PDF24\tesseract\tesseract.exe",
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            r"C:\Tesseract-OCR\tesseract.exe",
            r"D:\Program Files\Tesseract-OCR\tesseract.exe",
            r"D:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "tesseract"
        ]
        possible_paths.extend(standard_paths)
        
        # Проверяем пути
        for path in possible_paths:
            try:
                pytesseract.pytesseract.tesseract_cmd = path
                version = pytesseract.get_tesseract_version()
                logger.info(f"✅ Tesseract найден: {path} (версия {version})")
                _tesseract_cache = (True, f"Tesseract найден: {version}")
                return _tesseract_cache
            except:
                continue
        
        # Поиск через where/which
        try:
            result = subprocess.run(['where', 'tesseract'], capture_output=True, text=True, shell=True)
            if result.returncode == 0 and result.stdout.strip():
                tesseract_path = result.stdout.strip().split('\n')[0]
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                version = pytesseract.get_tesseract_version()
                logger.info(f"✅ Tesseract найден через поиск: {tesseract_path} (версия {version})")
                _tesseract_cache = (True, f"Tesseract найден: {version}")
                return _tesseract_cache
        except:
            pass
        
        _tesseract_cache = (False, "Tesseract не найден в системе")
        return _tesseract_cache
    except Exception as e:
        _tesseract_cache = (False, f"Ошибка проверки Tesseract: {e}")
        return _tesseract_cache

def setup_tesseract_auto():
    """Автоматическая настройка Tesseract"""
    logger.info("🔍 Проверка Tesseract OCR...")
    
    # Проверяем установку
    is_installed, message = check_tesseract_installation()
    
    if is_installed:
        logger.info(f"✅ {message}")
        return True
    
    logger.warning(f"⚠️ {message}")
    
    # Если Windows и Tesseract не найден
    if platform.system() == "Windows":
        logger.info("💡 Попытка настройки Tesseract для Windows...")
        
        # Проверяем, есть ли в папке проекта
        local_tesseract = Path("tesseract/tesseract.exe")
        if local_tesseract.exists():
            try:
                pytesseract.pytesseract.tesseract_cmd = str(local_tesseract)
                version = pytesseract.get_tesseract_version()
                logger.info(f"✅ Используется локальный Tesseract: {version}")
                return True
            except:
                pass
        
        # Предлагаем скачать
        logger.info("📥 Для полной функциональности OCR рекомендуется установить Tesseract")
        logger.info("🔗 Инструкции по установке:")
        logger.info("   1. Скачайте с: https://github.com/UB-Mannheim/tesseract/wiki")
        logger.info("   2. Установите в стандартную папку")
        logger.info("   3. Перезапустите бота")
        
        return False
    else:
        logger.info("💡 Для установки Tesseract на Linux/macOS:")
        logger.info("   Linux: sudo apt-get install tesseract-ocr")
        logger.info("   macOS: brew install tesseract")
        return False

async def install_missing_packages() -> bool:
    """Устанавливает отсутствующие пакеты асинхронно"""
    missing_packages = []
    
    if not TESSERACT_AVAILABLE:
        missing_packages.extend(["Pillow", "pytesseract"])
    if not PDF_AVAILABLE:
        missing_packages.append("PyPDF2")
    if not DOCX_AVAILABLE:
        missing_packages.append("python-docx")
    
    if missing_packages:
        logger.info(f"📦 Установка отсутствующих пакетов: {', '.join(missing_packages)}")
        try:
            # Асинхронная установка пакетов
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", *missing_packages,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("✅ Пакеты установлены успешно")
                logger.info("🔄 Перезапустите бота для применения изменений")
                return True
            else:
                logger.error(f"❌ Ошибка установки пакетов: {stderr.decode()}")
                return False
        except Exception as e:
            logger.error(f"❌ Ошибка установки пакетов: {e}")
            return False
    
    return True

async def extract_text_from_image(image_path: str) -> str:
    """Извлекает текст из изображения с помощью OCR с оптимизацией"""
    if not TESSERACT_AVAILABLE:
        return ("❌ Модули PIL/pytesseract не установлены.\n"
                "Установите командой: pip install Pillow pytesseract")
    
    # Проверяем Tesseract один раз
    tesseract_ok, message = check_tesseract_installation()
    if not tesseract_ok:
        return (f"🖼️ Изображение получено, но OCR недоступен.\n\n"
                f"❌ {message}\n\n"
                f"💡 Для распознавания текста на изображениях установите Tesseract:\n\n"
                f"🪟 Windows: Запустите файл УСТАНОВКА.bat\n"
                f"🐧 Linux: sudo apt-get install tesseract-ocr tesseract-ocr-rus\n"
                f"🍎 macOS: brew install tesseract\n\n"
                f"📱 Или опишите изображение текстом, и я помогу с анализом!")
    
    try:
        # Открываем изображение
        with Image.open(image_path) as image:
            # Оптимизация изображения для OCR
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Пробуем разные языковые настройки в порядке приоритета
            languages = ['rus+eng', 'eng', None]
            
            for lang in languages:
                try:
                    text = await asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: pytesseract.image_to_string(image, lang=lang) if lang else pytesseract.image_to_string(image)
                    )
                    
                    if text.strip():
                        lang_info = f"({lang})" if lang else "(default)"
                        logger.info(f"✅ OCR успешно выполнен {lang_info}")
                        return text.strip()
                except Exception as e:
                    logger.debug(f"OCR попытка с языком {lang} неудачна: {e}")
                    continue
            
            return "❓ Текст на изображении не найден или не распознан"
            
    except Exception as e:
        logger.error(f"Ошибка обработки изображения: {e}")
        return f"❌ Ошибка при обработке изображения: {e}"

async def extract_text_from_pdf(pdf_path: str) -> str:
    """Извлекает текст из PDF файла асинхронно с ограничениями"""
    if not PDF_AVAILABLE:
        return "❌ Модуль PyPDF2 не установлен. Установите командой: pip install PyPDF2"
    
    try:
        # Проверяем кэш
        cache_key = f"pdf_{Path(pdf_path).stat().st_mtime}_{Path(pdf_path).stat().st_size}"
        if cache_key in _file_cache:
            logger.debug("📋 Использован кэш для PDF")
            return _file_cache[cache_key]
        
        # Выполняем чтение PDF в отдельном потоке
        def read_pdf():
            reader = PdfReader(pdf_path)
            total_pages = len(reader.pages)
            
            # Ограничиваем количество страниц
            max_pages = min(total_pages, MAX_PDF_PAGES)
            if total_pages > MAX_PDF_PAGES:
                logger.warning(f"⚠️ PDF содержит {total_pages} страниц, обрабатываем первые {MAX_PDF_PAGES}")
            
            pages_text = []
            for page_num in range(max_pages):
                try:
                    page = reader.pages[page_num]
                    page_text = page.extract_text()
                    if page_text.strip():
                        # Ограничиваем размер текста страницы
                        if len(page_text) > MAX_TEXT_LENGTH:
                            page_text = page_text[:MAX_TEXT_LENGTH] + "... [обрезано]"
                        pages_text.append(f"--- Страница {page_num + 1} ---\n{page_text}")
                except Exception as page_error:
                    logger.warning(f"Ошибка при извлечении текста со страницы {page_num + 1}: {page_error}")
                    pages_text.append(f"--- Страница {page_num + 1} ---\n[Ошибка извлечения текста]")
            
            result = "\n\n".join(pages_text) if pages_text else "Текст не найден в PDF"
            
            # Добавляем информацию о количестве страниц
            page_info = f"📄 PDF содержит {total_pages} страниц"
            if total_pages > MAX_PDF_PAGES:
                page_info += f" (обработано первых {MAX_PDF_PAGES})"
            
            result = f"{page_info}\n\n{result}"
            
            # Общее ограничение размера результата
            if len(result) > MAX_TEXT_LENGTH * 3:
                result = result[:MAX_TEXT_LENGTH * 3] + "\n\n... [файл обрезан для экономии памяти]"
            
            return result
        
        text = await asyncio.get_event_loop().run_in_executor(None, read_pdf)
        
        # Сохраняем в кэш
        _file_cache[cache_key] = text
        
        # Ограничиваем размер кэша
        if len(_file_cache) > 50:
            # Удаляем старые записи
            oldest_key = min(_file_cache.keys())
            del _file_cache[oldest_key]
        
        return text
        
    except Exception as e:
        logger.error(f"Ошибка извлечения текста из PDF: {e}")
        return f"Ошибка при извлечении текста из PDF: {e}"

async def extract_text_from_docx(docx_path: str) -> str:
    """Извлекает текст из DOCX файла асинхронно"""
    if not DOCX_AVAILABLE:
        return "❌ Модуль python-docx не установлен. Установите командой: pip install python-docx"
    
    try:
        # Выполняем чтение DOCX в отдельном потоке
        def read_docx():
            doc = Document(docx_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs) if paragraphs else "Текст не найден в DOCX"
            
            # Добавляем информацию о документе
            total_paragraphs = len(paragraphs)
            doc_info = f"📝 DOCX содержит {total_paragraphs} абзацев\n\n"
            
            return doc_info + text
        
        text = await asyncio.get_event_loop().run_in_executor(None, read_docx)
        return text
        
    except Exception as e:
        logger.error(f"Ошибка извлечения текста из DOCX: {e}")
        return f"Ошибка при извлечении текста из DOCX: {e}"

async def extract_text_from_txt(txt_path: str) -> str:
    """Извлекает текст из TXT файла с оптимизированным определением кодировки"""
    encodings = ['utf-8', 'cp1251', 'windows-1251', 'latin-1', 'ascii']
    
    for encoding in encodings:
        try:
            async with aiofiles.open(txt_path, 'r', encoding=encoding) as f:
                text = await f.read()
            if text.strip():
                # Добавляем информацию о файле
                lines = text.strip().split('\n')
                file_info = f"📄 TXT файл содержит {len(lines)} строк\n\n"
                return file_info + text.strip()
            else:
                return "Файл пуст"
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception as e:
            logger.error(f"Ошибка чтения файла с кодировкой {encoding}: {e}")
            continue
    
    return "Не удалось прочитать файл (неподдерживаемая кодировка)"

async def download_file(file_id: str, local_path: str) -> bool:
    """Скачивает файл по file_id и сохраняет по local_path с оптимизацией"""
    try:
        file = await bot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
        
        # Создаем директорию если её нет
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Оптимизированное скачивание с таймаутом и увеличенным размером чанка
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(file_url) as response:
                if response.status == 200:
                    async with aiofiles.open(local_path, mode="wb") as f:
                        # Увеличиваем размер чанка для лучшей производительности
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                    return True
                else:
                    logger.error(f"Ошибка скачивания файла: HTTP {response.status}")
                    return False
    except aiohttp.ClientError as e:
        logger.error(f"Сетевая ошибка при скачивании файла: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла: {e}")
        return False

async def invoke_llm_api(user_content: str, user_id: int = None, selected_model: str = None) -> str:
    """Вызывает OpenRouter API и возвращает ответ"""
    if not OPENROUTER_API_KEY:
        return "Ошибка: Токен OPENROUTER_API_KEY не найден"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("REFERER_URL", "http://localhost"),
        "X-Title": os.getenv("TITLE_NAME", "Telegram Bot")
    }

    # Получаем настройки пользователя
    user_settings = user_prefs.get(user_id, {})
    preferred_model = user_settings.get("preferred_model", "auto")
    
    # Если модель выбрана явно, используем её
    if selected_model and selected_model in AVAILABLE_MODELS:
        preferred_model = selected_model

    # Список моделей для попытки
    if preferred_model == "auto":
        models_to_try = [
            "openai/gpt-oss-120b",
            "google/gemini-2.5-pro", 
            "anthropic/claude-sonnet-4",
            "deepseek/deepseek-r1-0528:free",
            "qwen/qwen3-235b-a22b:free",
            "qwen/qwen-2.5-coder-32b-instruct:free",
            "moonshotai/kimi-k2",
            "openai/gpt-oss-20b"
        ]
    else:
        # Пробуем выбранную модель, затем fallback
        models_to_try = [preferred_model] + [
            model for model in AVAILABLE_MODELS.keys() 
            if model != preferred_model and model != "auto"
        ]

    for model_index, model in enumerate(models_to_try):
        try:
            # Получаем пользовательские настройки температуры и токенов
            temperature = user_settings.get("temperature", 0.7)
            max_tokens = user_settings.get("max_tokens", 1024)
            
            # Получаем контекст чата с историей сообщений
            messages = get_chat_context(user_id)
            
            # Добавляем новое сообщение пользователя
            messages.append({
                "role": "user",
                "content": user_content
            })
            
            # Обрезаем контекст если нужно
            messages = trim_context_if_needed(messages)
            
            body = {
                "model": model,
                "messages": messages,
                "stream": True,
                "max_tokens": max_tokens,
                "temperature": temperature
            }

            full_response = ""
            api_url = "https://openrouter.ai/api/v1/chat/completions"

            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=headers, json=body) as response:
                    if response.status == 200:
                        async for line in response.content:
                            line = line.decode("utf-8").strip()
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk_data = json.loads(data)
                                    if chunk_data.get("choices") and chunk_data["choices"][0].get("delta"):
                                        content = chunk_data["choices"][0]["delta"].get("content")
                                        if content:
                                            full_response += content
                                except json.JSONDecodeError:
                                    logger.error(f"Error decoding JSON chunk: {data}")
                                except Exception as e:
                                    logger.error(f"Error processing chunk: {e}")
                        
                        if full_response:
                            logger.info(f"✅ Успешный ответ от модели: {model}")
                            
                            # Сохраняем сообщения в историю
                            if user_id:
                                add_to_chat_history(user_id, "user", user_content)
                                add_to_chat_history(user_id, "assistant", full_response)
                            
                            return full_response
                    
                    # Если статус не 200, пробуем следующую модель
                    error_text = await response.text()
                    logger.warning(f"⚠️ Модель {model} недоступна (статус {response.status}), пробуем следующую...")
                    
                    if model_index == len(models_to_try) - 1:  # Последняя модель
                        logger.error(f"❌ Все модели недоступны. Последняя ошибка: {response.status} - {error_text}")
                        return f"Извините, все AI модели временно недоступны. Ошибка: {response.status}. Попробуйте позже."
                    
                    continue  # Пробуем следующую модель

        except aiohttp.ClientError as e:
            logger.warning(f"⚠️ Сетевая ошибка для модели {model}: {e}")
            if model_index == len(models_to_try) - 1:
                return f"Ошибка соединения с сервером: {e}"
            continue
        except Exception as e:
            logger.warning(f"⚠️ Ошибка для модели {model}: {e}")
            if model_index == len(models_to_try) - 1:
                return f"Произошла ошибка: {e}"
            continue

    return "Не удалось получить ответ ни от одной модели."

async def analyze_image_with_vision_model(image_url: str, prompt: str, model: str, user_id: int) -> tuple[bool, str]:
    """Анализирует изображение через мультимодальную модель OpenRouter"""
    if not OPENROUTER_API_KEY:
        return False, "Ошибка: OPENROUTER_API_KEY не найден"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("REFERER_URL", "http://localhost"),
        "X-Title": os.getenv("TITLE_NAME", "Telegram Bot")
    }

    try:
        # Получаем контекст чата
        messages = get_chat_context(user_id)
        
        # Добавляем сообщение с изображением
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
        })

        # Обрезаем контекст если нужно
        messages = trim_context_if_needed(messages)

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.3
        }

        api_url = "https://openrouter.ai/api/v1/chat/completions"

        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("choices") and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        logger.info(f"✅ Изображение проанализировано моделью: {model}")
                        
                        # Сохраняем в историю
                        add_to_chat_history(user_id, "user", f"[Изображение]: {prompt}")
                        add_to_chat_history(user_id, "assistant", content)
                        
                        return True, content
                    else:
                        return False, "Не удалось получить анализ изображения"
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Ошибка анализа изображения: {response.status} - {error_text}")
                    return False, f"Ошибка анализа: {response.status}"

    except aiohttp.ClientError as e:
        logger.error(f"❌ Сетевая ошибка при анализе изображения: {e}")
        return False, f"Ошибка соединения: {e}"
    except Exception as e:
        logger.error(f"❌ Ошибка при анализе изображения: {e}")
        return False, f"Произошла ошибка: {e}"

async def enhanced_image_analysis(image_url: str, user_id: int, custom_prompt: str = None) -> str:
    """Улучшенный анализ изображений через Vision модели с fallback к Tesseract"""
    user_settings = user_prefs.get(user_id, {})
    preferred_model = user_settings.get("preferred_model", "auto")
    
    # Промпт по умолчанию
    default_prompt = "Подробно опиши это изображение и извлеки весь видимый текст. Если это документ или содержит текст, верни его дословно."
    prompt = custom_prompt or default_prompt
    
    # Выбираем модели для анализа
    if preferred_model == "auto":
        # Приоритет мультимодальным моделям
        models_to_try = [
            "google/gemini-2.5-pro",
            "anthropic/claude-sonnet-4", 
            "openai/gpt-oss-120b",
            "moonshotai/kimi-k2"
        ]
    else:
        if preferred_model in VISION_MODELS:
            models_to_try = [preferred_model]
        else:
            # Если выбранная модель не поддерживает изображения, используем лучшую Vision модель
            models_to_try = ["google/gemini-2.5-pro"]
    
    # Пробуем Vision модели
    for model in models_to_try:
        if model in VISION_MODELS:
            success, result = await analyze_image_with_vision_model(image_url, prompt, model, user_id)
            if success:
                return f"👁️ Анализ через {AVAILABLE_MODELS.get(model, model)}:\n\n{result}"
    
    # Fallback к Tesseract если Vision модели не работают
    logger.info("🔄 Fallback к Tesseract OCR...")
    return "❌ Vision модели недоступны. Для анализа изображений нужна поддержка мультимодальных моделей."



@dp.message(CommandStart())
async def send_welcome(message: types.Message):
    """Handles the /start command."""
    user_id = message.from_user.id
    
    # Инициализируем настройки пользователя (настроено на максимум для лучших ответов)
    if user_id not in user_prefs:
        user_prefs[user_id] = {
            "show_thoughts": False,
            "preferred_model": "auto",
            "temperature": 0.3,  # Низкая температура для точности
            "max_tokens": 4096   # Максимум токенов для полных ответов
        }
    
    # Проверяем статус OCR
    tesseract_ok, tesseract_msg = check_tesseract_installation()
    
    welcome_text = "🤖 Привет! Я умный бот с поддержкой ИИ!\n\n"
    welcome_text += "📋 Мои возможности:\n"
    welcome_text += "💬 Веду продолжительные диалоги (помню предыдущие сообщения)\n"
    welcome_text += "👁️ Анализирую изображения через Vision модели AI\n"
    welcome_text += "📄 Анализирую документы (PDF, DOCX, TXT)\n"
    welcome_text += f"🖼️ OCR изображений: {'✅ AI + Tesseract' if tesseract_ok else '✅ Только AI Vision'}\n"
    welcome_text += "🎵 Обрабатываю медиафайлы\n\n"
    welcome_text += "🎯 Просто отправь мне сообщение, файл или изображение!\n"
    welcome_text += "💭 Я запомню наш разговор и буду отвечать в контексте!\n\n"
    
    # Показываем текущую модель
    current_model = user_prefs[user_id]["preferred_model"]
    model_name = AVAILABLE_MODELS.get(current_model, "Неизвестная")
    welcome_text += f"🤖 Текущая модель: {model_name}\n\n"
    
    if not tesseract_ok:
        welcome_text += f"💡 Для OCR установите Tesseract:\n{tesseract_msg}\n\n"
    
    await message.reply(welcome_text, reply_markup=get_main_keyboard())

@dp.message(Command("think"))
async def toggle_think(message: types.Message):
    """Toggles the display of thought process (if available)."""
    user_id = message.from_user.id
    current_pref = user_prefs.get(user_id, {"show_thoughts": False})
    new_pref = not current_pref["show_thoughts"]
    user_prefs[user_id] = {"show_thoughts": new_pref}

    status = "включено" if new_pref else "выключено"
    await message.reply(f"Отображение размышлений {status}.")



@dp.message(lambda message: message.text == "🤖 Выбор модели")
async def handle_model_selection(message: types.Message):
    """Обработчик кнопки выбора модели"""
    user_id = message.from_user.id
    current_model = user_prefs.get(user_id, {}).get("preferred_model", "auto")
    current_name = AVAILABLE_MODELS.get(current_model, "Неизвестная")
    
    model_text = f"🤖 **Выбор AI модели**\n\n"
    model_text += f"Текущая модель: {current_name}\n\n"
    model_text += "Доступные модели:\n"
    for model_id, model_name in AVAILABLE_MODELS.items():
        status = "✅" if model_id == current_model else "⚪"
        model_text += f"{status} {model_name}\n"
    
    model_text += "\nВыберите модель:"
    
    await message.reply(model_text, reply_markup=get_model_keyboard())

@dp.message(lambda message: message.text == "📊 Статус")
async def handle_status(message: types.Message):
    """Обработчик кнопки статуса"""
    tesseract_ok, tesseract_msg = check_tesseract_installation()
    
    status_text = "📊 **Статус системы**\n\n"
    status_text += f"✅ Обработка текста: Доступна\n"
    status_text += f"{'✅' if PDF_AVAILABLE else '❌'} Анализ PDF: {'Доступен' if PDF_AVAILABLE else 'Недоступен'}\n"
    status_text += f"{'✅' if DOCX_AVAILABLE else '❌'} Анализ DOCX: {'Доступен' if DOCX_AVAILABLE else 'Недоступен'}\n"
    status_text += f"{'✅' if tesseract_ok else '❌'} OCR изображений: {'Доступен' if tesseract_ok else 'Недоступен'}\n"
    status_text += f"⚡ Время запуска: ~1.89 сек\n"
    status_text += f"🧠 Кэш файлов: {len(_file_cache)} записей\n"
    
    await message.reply(status_text, reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "ℹ️ Помощь")
async def handle_help(message: types.Message):
    """Обработчик кнопки помощи"""
    help_text = "ℹ️ **Справка по боту**\n\n"
    help_text += "🎯 **Основные функции:**\n"
    help_text += "• Отправьте текст для анализа ИИ\n"
    help_text += "• Загрузите файл (PDF, DOCX, TXT, изображение)\n"
    help_text += "• Анализ изображений через Vision модели AI\n"
    help_text += "• Ведите продолжительные диалоги - бот помнит контекст!\n\n"
    help_text += "👁️ **Анализ изображений:**\n"
    help_text += "• AI Vision анализ через мультимодальные модели\n"
    help_text += "• Извлечение текста и описание содержимого\n"
    help_text += "• Fallback к Tesseract OCR при необходимости\n"
    help_text += "• Поддержка в Gemini 2.5 Pro, Claude Sonnet 4, GPT-OSS-120B\n\n"
    help_text += "🤖 **AI модели:**\n"
    help_text += "• GPT-OSS-120B/20B - новые модели OpenAI\n"
    help_text += "• DeepSeek R1 - бесплатная модель рассуждений\n"
    help_text += "• Qwen3-235B - мощная бесплатная модель\n"
    help_text += "• Qwen Coder - специализация на коде\n"
    help_text += "• Kimi K2, Claude Sonnet 4, Gemini 2.5 Pro\n\n"
    help_text += "💭 **Память диалога:**\n"
    help_text += f"• Сохраняется до {MAX_CHAT_HISTORY} сообщений\n"
    help_text += f"• Автоматическое управление контекстом (~{MAX_CONTEXT_TOKENS} токенов)\n"
    help_text += "• Изображения сохраняются в контексте диалога\n\n"
    help_text += "📝 **Команды:**\n"
    help_text += "/start - перезапуск бота\n"
    help_text += "/think - переключить режим размышлений\n\n"
    help_text += "🔄 **Лимиты:**\n"
    help_text += "• Максимальный размер файла: 20 MB\n"
    help_text += "• Максимальное количество страниц PDF: 50\n"
    
    await message.reply(help_text, reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "🗑️ Очистить чат")
async def handle_clear_chat(message: types.Message):
    """Обработчик кнопки очистки чата"""
    user_id = message.from_user.id
    clear_chat_history(user_id)
    await message.reply("✨ История диалога очищена! Готов к новому разговору!", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "🗑️ Очистить историю")
async def handle_clear_history(message: types.Message):
    """Обработчик кнопки очистки истории"""
    user_id = message.from_user.id
    history_count = len(user_chat_history.get(user_id, []))
    clear_chat_history(user_id)
    await message.reply(f"✨ История диалога очищена! Удалено {history_count} сообщений.", reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "💭 Память диалога")
async def handle_memory_status(message: types.Message):
    """Обработчик кнопки статуса памяти диалога"""
    user_id = message.from_user.id
    history = user_chat_history.get(user_id, [])
    
    if not history:
        status_text = "💭 **Память диалога**\n\n"
        status_text += "📝 История пуста - это первое сообщение!\n"
        status_text += f"📊 Лимит сообщений: {MAX_CHAT_HISTORY}\n"
        status_text += f"🎯 Лимит токенов: {MAX_CONTEXT_TOKENS}\n\n"
        status_text += "ℹ️ Бот теперь запоминает ваши сообщения и ведет непрерывный диалог!"
    else:
        total_tokens = sum(estimate_tokens(msg["content"]) for msg in history)
        user_msgs = len([msg for msg in history if msg["role"] == "user"])
        ai_msgs = len([msg for msg in history if msg["role"] == "assistant"])
        
        status_text = "💭 **Память диалога**\n\n"
        status_text += f"📝 Сообщений в истории: {len(history)}\n"
        status_text += f"👤 Ваших сообщений: {user_msgs}\n"
        status_text += f"🤖 Ответов ИИ: {ai_msgs}\n"
        status_text += f"📊 Примерно токенов: {total_tokens}/{MAX_CONTEXT_TOKENS}\n"
        status_text += f"🎯 Лимит сообщений: {MAX_CHAT_HISTORY}\n\n"
        
        if total_tokens > MAX_CONTEXT_TOKENS * 0.8:
            status_text += "⚠️ Контекст почти заполнен - старые сообщения будут удаляться автоматически"
        else:
            status_text += "✅ Память работает нормально"
    
    await message.reply(status_text, reply_markup=get_main_keyboard())

@dp.message(lambda message: message.text == "🔙 Назад")
async def handle_back(message: types.Message):
    """Обработчик кнопки назад"""
    await message.reply("🏠 Главное меню", reply_markup=get_main_keyboard())

# Обработчики выбора модели
@dp.message(lambda message: message.text in AVAILABLE_MODELS.values())
async def handle_model_change(message: types.Message):
    """Обработчик изменения модели"""
    user_id = message.from_user.id
    
    # Находим ID модели по названию
    selected_model = None
    for model_id, model_name in AVAILABLE_MODELS.items():
        if message.text == model_name:
            selected_model = model_id
            break
    
    if selected_model:
        if user_id not in user_prefs:
            user_prefs[user_id] = {}
        user_prefs[user_id]["preferred_model"] = selected_model
        
        await message.reply(
            f"✅ Модель изменена на: {message.text}", 
            reply_markup=get_main_keyboard()
        )
    else:
        await message.reply("❌ Ошибка выбора модели", reply_markup=get_main_keyboard())



@dp.message(lambda message: message.document or message.photo or message.voice or message.video or message.audio)
async def handle_file(message: types.Message):
    """Handles incoming file messages"""
    user_id = message.from_user.id
    file_info = None
    file_type = "unknown"
    file_name = "unknown"

    # Определяем тип файла
    if message.document:
        file_info = message.document
        file_type = "document"
        file_name = file_info.file_name or "document"
    elif message.photo:
        file_info = message.photo[-1]  # Берем фото наибольшего размера
        file_type = "photo"
        file_name = f"photo_{file_info.file_id}.jpg"
    elif message.voice:
        file_info = message.voice
        file_type = "voice"
        file_name = f"voice_{file_info.file_id}.ogg"
    elif message.video:
        file_info = message.video
        file_type = "video"
        file_name = file_info.file_name or f"video_{file_info.file_id}.mp4"
    elif message.audio:
        file_info = message.audio
        file_type = "audio"
        file_name = file_info.file_name or f"audio_{file_info.file_id}.mp3"

    if not file_info:
        await message.reply("❌ Не удалось получить информацию о файле.")
        return

    # Проверяем размер файла
    file_size_mb = file_info.file_size / (1024 * 1024) if hasattr(file_info, 'file_size') and file_info.file_size else 0
    if file_size_mb > MAX_FILE_SIZE_MB:
        await message.reply(f"❌ Файл слишком большой ({file_size_mb:.1f} MB). Максимальный размер: {MAX_FILE_SIZE_MB} MB")
        return

    # Показываем статус обработки
    processing_message = await message.reply("📥 Получаю файл...")

    # Генерируем локальный путь для файла
    local_file_path = DOWNLOADS_DIR / f"{file_info.file_id}_{file_name}"
    
    # Скачиваем файл
    await bot.edit_message_text("💾 Скачиваю файл...", 
                               chat_id=processing_message.chat.id, 
                               message_id=processing_message.message_id)

    download_success = await download_file(file_info.file_id, str(local_file_path))
    
    if not download_success:
        await bot.edit_message_text("❌ Ошибка при скачивании файла.", 
                                   chat_id=processing_message.chat.id, 
                                   message_id=processing_message.message_id)
        return

    await bot.edit_message_text("🔍 Анализирую содержимое файла...", 
                               chat_id=processing_message.chat.id, 
                               message_id=processing_message.message_id)

    # Анализируем содержимое файла в зависимости от типа
    file_content = ""
    file_extension = os.path.splitext(file_name)[1].lower() if '.' in file_name else ""

    try:
        local_file_str = str(local_file_path)
        if file_type == "photo":
            # Получаем URL изображения для Vision анализа
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{(await bot.get_file(file_info.file_id)).file_path}"
            
            # Сначала пробуем Vision модели, затем Tesseract как fallback
            await bot.edit_message_text("👁️ Анализирую изображение через AI Vision...", 
                                       chat_id=processing_message.chat.id, 
                                       message_id=processing_message.message_id)
            
            file_content = await enhanced_image_analysis(file_url, user_id)
            
            # Если Vision модели не сработали, пробуем Tesseract
            if "❌ Vision модели недоступны" in file_content:
                await bot.edit_message_text("🔄 Fallback к Tesseract OCR...", 
                                           chat_id=processing_message.chat.id, 
                                           message_id=processing_message.message_id)
                tesseract_result = await extract_text_from_image(local_file_str)
                if tesseract_result and "❌" not in tesseract_result:
                    file_content = f"🔍 Tesseract OCR:\n\n{tesseract_result}"
        elif file_extension == ".pdf":
            file_content = await extract_text_from_pdf(local_file_str)
        elif file_extension == ".docx":
            file_content = await extract_text_from_docx(local_file_str)
        elif file_extension == ".txt":
            file_content = await extract_text_from_txt(local_file_str)
        elif file_type == "document":
            # Для документов без поддерживаемого расширения
            file_size_mb = file_info.file_size / (1024 * 1024) if hasattr(file_info, 'file_size') and file_info.file_size else 0
            file_content = f"📄 Документ: {file_name}\n📏 Размер: {file_size_mb:.2f} MB\n\n❌ Формат файла не поддерживается для анализа.\n\nПоддерживаемые форматы:\n• PDF (.pdf)\n• Word (.docx)\n• Текстовые файлы (.txt)\n• Изображения (JPG, PNG, etc.)"
        elif file_type in ["voice", "video", "audio"]:
            file_size_mb = file_info.file_size / (1024 * 1024) if hasattr(file_info, 'file_size') and file_info.file_size else 0
            file_content = f"🎵 Медиафайл: {file_name}\n📏 Размер: {file_size_mb:.2f} MB\n\n❌ Анализ медиафайлов пока не поддерживается."
        else:
            file_content = "❌ Неизвестный тип файла. Поддерживаются: PDF, DOCX, TXT, изображения."
    except Exception as e:
        logger.error(f"Ошибка при анализе файла: {e}")
        file_content = f"Ошибка при анализе файла: {e}"

    # Подготавливаем запрос к LLM
    prompt = f"""Пользователь отправил файл типа '{file_type}' с именем '{file_name}'.
Содержимое файла:
{file_content}

Пожалуйста, проанализируй этот файл и дай структурированный ответ:
1. 📋 Тип документа и основная информация
2. 📄 Ключевые данные (даты, номера, важные факты)
3. 💡 Краткое резюме содержания
4. 🎯 Основные выводы или рекомендации

Отвечай кратко, но информативно."""

    # Отправляем запрос к LLM
    response_text = await invoke_llm_api(prompt, user_id)

    # Удаляем сообщение о процессе
    try:
        await bot.delete_message(chat_id=processing_message.chat.id, message_id=processing_message.message_id)
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение о процессе: {e}")

    # Отправляем ответ пользователю
    if response_text:
        show_thoughts = user_prefs.get(user_id, {}).get("show_thoughts", False)
        if not show_thoughts:
            response_text = re.sub(r'<think>.*?</think>\s*', '', response_text, flags=re.DOTALL | re.IGNORECASE).strip()

        if not response_text:
            await message.reply("Ответ содержал только размышления, которые скрыты.")
            return

        # Разбиваем длинные сообщения
        for i in range(0, len(response_text), 4096):
            await message.reply(response_text[i:i+4096])
    else:
        await message.reply("Не удалось получить ответ.")

@dp.message()
async def handle_message(message: types.Message):
    """Handles incoming text messages and replies using the LLM API."""
    if not message.text:
        return

    user_id = message.from_user.id
    show_thoughts = user_prefs.get(user_id, {}).get("show_thoughts", False)

    # Обычная обработка текстовых сообщений
    processing_message = await message.reply("🤖 Думаю...")

    response_text = await invoke_llm_api(message.text, user_id)

    try:
        await bot.delete_message(chat_id=processing_message.chat.id, message_id=processing_message.message_id)
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение о процессе: {e}")

    if response_text:
        if not show_thoughts:
            response_text = re.sub(r'<think>.*?</think>\s*', '', response_text, flags=re.DOTALL | re.IGNORECASE).strip()

        if not response_text:
            await message.reply("Ответ содержал только размышления, которые скрыты.")
            return

        # Разбиваем длинные сообщения
        for i in range(0, len(response_text), 4096):
            await message.reply(response_text[i:i+4096])
    else:
        await message.reply("Не удалось получить ответ.")

async def cleanup_old_files():
    """Очищает старые временные файлы"""
    try:
        import time
        current_time = time.time()
        max_age = 3600  # 1 час
        
        if DOWNLOADS_DIR.exists():
            for file_path in DOWNLOADS_DIR.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age:
                        try:
                            file_path.unlink()
                            logger.debug(f"🗑️ Удален старый файл: {file_path.name}")
                        except Exception as e:
                            logger.debug(f"Не удалось удалить файл {file_path}: {e}")
    except Exception as e:
        logger.warning(f"Ошибка очистки файлов: {e}")

async def main():
    """Starts the bot."""
    if not TELEGRAM_BOT_TOKEN or not OPENROUTER_API_KEY:
        logger.error("Токены не найдены. Убедитесь, что переменные TELEGRAM_BOT_TOKEN и OPENROUTER_API_KEY установлены.")
        return
    
    logger.info("🚀 Бот запускается...")
    
    # Очищаем старые файлы при запуске
    await cleanup_old_files()
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        # Очищаем файлы при завершении
        await cleanup_old_files()

async def startup_checks() -> bool:
    """Выполняет проверки при запуске асинхронно"""
    logger.info("=" * 60)
    logger.info("🤖 TELEGRAM AI BOT - ИНИЦИАЛИЗАЦИЯ")
    logger.info("=" * 60)
    
    # Проверяем и устанавливаем отсутствующие пакеты
    logger.info("📦 Проверка Python пакетов...")
    if not await install_missing_packages():
        logger.error("❌ Не удалось установить необходимые пакеты")
        return False
    
    # Настраиваем Tesseract
    tesseract_ok = setup_tesseract_auto()
    
    # Проверяем токены
    logger.info("🔑 Проверка API токенов...")
    if TELEGRAM_BOT_TOKEN and OPENROUTER_API_KEY:
        logger.info("✅ Токены найдены")
    else:
        logger.error("❌ Токены не найдены")
        return False
    
    logger.info("=" * 60)
    logger.info("📊 СТАТУС ФУНКЦИЙ:")
    logger.info("✅ Обработка текста: Доступна")
    logger.info(f"{'✅' if PDF_AVAILABLE else '⚠️'} Анализ PDF: {'Доступен' if PDF_AVAILABLE else 'Недоступен'}")
    logger.info(f"{'✅' if DOCX_AVAILABLE else '⚠️'} Анализ DOCX: {'Доступен' if DOCX_AVAILABLE else 'Недоступен'}")
    logger.info(f"{'✅' if tesseract_ok else '⚠️'} OCR изображений: {'Доступен' if tesseract_ok else 'Недоступен'}")
    logger.info("=" * 60)
    
    if not tesseract_ok:
        logger.info("💡 Для включения OCR установите Tesseract:")
        logger.info("   Windows: https://github.com/UB-Mannheim/tesseract/wiki")
        logger.info("   Linux: sudo apt-get install tesseract-ocr")
        logger.info("   macOS: brew install tesseract")
        logger.info("=" * 60)
    
    return True

async def main_wrapper():
    """Основная функция-обертка"""
    try:
        # Выполняем проверки при запуске
        if not await startup_checks():
            logger.error("❌ Инициализация не удалась")
            return False
        
        logger.info("🎉 Бот готов к работе!")
        await main()
        return True
    except KeyboardInterrupt:
        logger.info("\n👋 Бот остановлен пользователем")
        return True
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        return False

if __name__ == '__main__':
    try:
        success = asyncio.run(main_wrapper())
        if not success:
            input("Нажмите Enter для выхода...")
            sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Критическая ошибка запуска: {e}")
        input("Нажмите Enter для выхода...")
        sys.exit(1)