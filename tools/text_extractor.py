
import asyncio
import logging
from pathlib import Path
import aiofiles
import platform
import subprocess
from functools import lru_cache
from typing import Tuple
import sys

# Условные импорты
try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    Image = None
    TESSERACT_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PDF_AVAILABLE = True
except ImportError:
    fitz = None
    PDF_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    Document = None
    DOCX_AVAILABLE = False

logger = logging.getLogger(__name__)

# Константы и кэш
_file_cache = {}
_tesseract_cache = None
MAX_PDF_PAGES = 50
MAX_TEXT_LENGTH = 10000
CONFIG_DIR = Path("config")
CONFIG_DIR.mkdir(exist_ok=True)

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

        config_file = CONFIG_DIR / 'tesseract_path.txt'
        possible_paths = []

        if config_file.exists():
            try:
                saved_path = config_file.read_text().strip()
                if saved_path and Path(saved_path).exists():
                    possible_paths.append(saved_path)
            except:
                pass

        standard_paths = [
            r"C:\\Users\\User-01\\AppData\\Local\\Programs\\Tesseract-OCR\\tesseract.exe",
            r"C:\\Program Files\\PDF24\\tesseract\\tesseract.exe",
            r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
            r"C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
            r"C:\\Tesseract-OCR\\tesseract.exe",
            r"D:\\Program Files\\Tesseract-OCR\\tesseract.exe",
            r"D:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe",
            "tesseract"
        ]
        possible_paths.extend(standard_paths)

        for path in possible_paths:
            try:
                pytesseract.pytesseract.tesseract_cmd = path
                version = pytesseract.get_tesseract_version()
                logger.info(f"✅ Tesseract найден: {path} (версия {version})")
                _tesseract_cache = (True, f"Tesseract найден: {version}")
                return _tesseract_cache
            except:
                continue

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

    is_installed, message = check_tesseract_installation()

    if is_installed:
        logger.info(f"✅ {message}")
        return True

    logger.warning(f"⚠️ {message}")

    if platform.system() == "Windows":
        logger.info("💡 Попытка настройки Tesseract для Windows...")

        local_tesseract = Path("tesseract/tesseract.exe")
        if local_tesseract.exists():
            try:
                pytesseract.pytesseract.tesseract_cmd = str(local_tesseract)
                version = pytesseract.get_tesseract_version()
                logger.info(f"✅ Используется локальный Tesseract: {version}")
                return True
            except:
                pass

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
        missing_packages.append("PyMuPDF")
    if not DOCX_AVAILABLE:
        missing_packages.append("python-docx")

    if missing_packages:
        logger.info(f"📦 Установка отсутствующих пакетов: {', '.join(missing_packages)}")
        try:
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
    """Извлекает текст из изображения с помощью OCR с оптимизацией и кэшированием."""
    if not TESSERACT_AVAILABLE:
        return ("❌ Модули PIL/pytesseract не установлены.\n"
                "Установите командой: pip install Pillow pytesseract")

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
        cache_key = f"ocr_{Path(image_path).stat().st_mtime}_{Path(image_path).stat().st_size}"
        if cache_key in _file_cache:
            logger.debug("📋 Использован кэш для OCR")
            return _file_cache[cache_key]

        with Image.open(image_path) as image:
            grayscale_image = image.convert('L')
            lang = 'rus+eng'

            try:
                text = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: pytesseract.image_to_string(grayscale_image, lang=lang)
                )

                result = text.strip() if text.strip() else "❓ Текст на изображении не найден или не распознан"

                _file_cache[cache_key] = result
                logger.info(f"✅ OCR успешно выполнен ({lang})")

                # Ограничиваем размер кэша
                if len(_file_cache) > 50:
                    oldest_key = min(_file_cache.keys())
                    del _file_cache[oldest_key]

                return result
            except Exception as e:
                logger.error(f"Ошибка OCR с языком {lang}: {e}")
                return "❓ Ошибка при распознавании текста."

    except Exception as e:
        logger.error(f"Ошибка обработки изображения: {e}")
        return f"❌ Ошибка при обработке изображения: {e}"

async def extract_text_from_pdf(pdf_path: str) -> str:
    """Извлекает текст из PDF файла асинхронно с использованием PyMuPDF."""
    if not PDF_AVAILABLE:
        return "❌ Модуль PyMuPDF не установлен. Установите командой: pip install PyMuPDF"

    try:
        cache_key = f"pdf_{Path(pdf_path).stat().st_mtime}_{Path(pdf_path).stat().st_size}"
        if cache_key in _file_cache:
            logger.debug("📋 Использован кэш для PDF")
            return _file_cache[cache_key]

        def read_pdf():
            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            max_pages = min(total_pages, MAX_PDF_PAGES)
            if total_pages > MAX_PDF_PAGES:
                logger.warning(f"⚠️ PDF содержит {total_pages} страниц, обрабатываем первые {MAX_PDF_PAGES}")

            pages_text = []
            for page_num in range(max_pages):
                try:
                    page = doc.load_page(page_num)
                    page_text = page.get_text("text")
                    if page_text.strip():
                        if len(page_text) > MAX_TEXT_LENGTH:
                            page_text = page_text[:MAX_TEXT_LENGTH] + "... [обрезано]"
                        pages_text.append(f"--- Страница {page_num + 1} ---\n{page_text}")
                except Exception as page_error:
                    logger.warning(f"Ошибка при извлечении текста со страницы {page_num + 1}: {page_error}")
                    pages_text.append(f"--- Страница {page_num + 1} ---\n[Ошибка извлечения текста]")

            doc.close()
            result = "\n\n".join(pages_text) if pages_text else "Текст не найден в PDF"

            page_info = f"📄 PDF содержит {total_pages} страниц"
            if total_pages > MAX_PDF_PAGES:
                page_info += f" (обработано первых {MAX_PDF_PAGES})"

            result = f"{page_info}\n\n{result}"

            if len(result) > MAX_TEXT_LENGTH * 3:
                result = result[:MAX_TEXT_LENGTH * 3] + "\n\n... [файл обрезан для экономии памяти]"

            return result

        text = await asyncio.get_event_loop().run_in_executor(None, read_pdf)

        _file_cache[cache_key] = text

        if len(_file_cache) > 50:
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
        def read_docx():
            doc = Document(docx_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs) if paragraphs else "Текст не найден в DOCX"

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
