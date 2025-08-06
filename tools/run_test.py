#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Простой тест бота - запускается двойным щелчком
"""

import sys
import os

def test_bot_functionality():
    """Дополнительная проверка функциональности бота"""
    print("\n🤖 Тестирование функций бота:")
    
    try:
        # Проверяем импорт основных функций
        import importlib.util
        spec = importlib.util.spec_from_file_location("bot_module", "telegram_ai_bot.py")
        bot_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bot_module)
        print("✅ Основной бот успешно загружен")
        
        # Проверяем наличие основных функций
        if hasattr(bot_module, 'invoke_llm_api'):
            print("✅ Функция API найдена")
        if hasattr(bot_module, 'extract_text_from_image'):
            print("✅ Функция OCR найдена")
        if hasattr(bot_module, 'extract_text_from_pdf'):
            print("✅ Функция PDF найдена")
            
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки бота: {e}")
        return False

def main():
    print("=" * 60)
    print("🧪 ТЕСТИРОВАНИЕ TELEGRAM BOT")
    print("=" * 60)
    
    # Проверяем Python
    print(f"Python версия: {sys.version}")
    
    # Проверяем файлы
    print("\n📁 Проверка файлов:")
    files = ['telegram_ai_bot.py', 'requirements.txt', 'README.md']
    for file in files:
        if os.path.exists(file):
            print(f"✅ {file} - найден")
        else:
            print(f"❌ {file} - НЕ НАЙДЕН")
    
    # Проверяем зависимости
    print("\n📦 Проверка зависимостей:")
    deps = ['aiogram', 'aiohttp', 'aiofiles', 'PIL', 'pytesseract', 'PyPDF2', 'docx']
    missing = []
    
    for dep in deps:
        try:
            if dep == 'PIL':
                import PIL
            elif dep == 'docx':
                import docx
            else:
                __import__(dep)
            print(f"✅ {dep}")
        except ImportError:
            print(f"❌ {dep} - НЕ УСТАНОВЛЕН")
            missing.append(dep)
    
    # Проверяем синтаксис
    print("\n🔍 Проверка синтаксиса:")
    syntax_ok = True
    try:
        with open('telegram_ai_bot.py', 'r', encoding='utf-8') as f:
            compile(f.read(), 'telegram_ai_bot.py', 'exec')
        print("✅ telegram_ai_bot.py - синтаксис корректен")
    except Exception as e:
        print(f"❌ telegram_ai_bot.py - ошибка: {e}")
        syntax_ok = False
    
    # Проверяем структуру папок
    print("\n📂 Проверка структуры:")
    folders = ['config', 'docs', 'tools', 'downloads', 'tesseract']
    for folder in folders:
        if os.path.exists(folder):
            print(f"✅ {folder}/ - найдена")
        else:
            print(f"⚠️ {folder}/ - не найдена")
    
    # Тестируем функциональность бота
    if syntax_ok and not missing:
        bot_ok = test_bot_functionality()
    else:
        bot_ok = False
    
    # Результаты
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ:")
    
    if missing:
        print(f"❌ Отсутствуют зависимости: {', '.join(missing)}")
        print("\n💡 Для установки зависимостей:")
        print("1. Откройте командную строку в этой папке")
        print("2. Выполните: pip install -r requirements.txt")
    else:
        print("✅ Все зависимости установлены!")
    
    if syntax_ok:
        print("✅ Синтаксис файлов корректен!")
    else:
        print("❌ Есть синтаксические ошибки!")
    
    if bot_ok:
        print("✅ Функции бота работают!")
    
    print("\n🚀 Для запуска бота:")
    print("1. Дважды щелкните Запуск_AI_Бота.bat")
    print("2. Или выполните: python telegram_ai_bot.py")
    
    if not missing and syntax_ok and bot_ok:
        print("\n🎉 Бот готов к запуску!")
    
    print("\n" + "=" * 60)
    input("Нажмите Enter для выхода...")

if __name__ == "__main__":
    main() 