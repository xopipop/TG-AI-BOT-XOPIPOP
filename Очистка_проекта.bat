@echo off
chcp 65001 >nul
echo ████████████████████████████████████████████████████████████████████████████████
echo █                     🧹 ОЧИСТКА AI ПРОЕКТА                                   █
echo ████████████████████████████████████████████████████████████████████████████████
echo.
echo 🗑️ Очистка временных файлов проекта...
echo.

echo 📁 Очистка загруженных файлов...
python -c "import os, shutil; files = [f for f in os.listdir('downloads') if os.path.isfile(os.path.join('downloads', f))]; [os.remove(os.path.join('downloads', f)) for f in files]; print(f'   ✅ Удалено {len(files)} файлов')"

echo.
echo 🐍 Очистка кэша Python...
python -c "import shutil; shutil.rmtree('__pycache__', ignore_errors=True); print('   ✅ Кэш очищен')"

echo.
echo 📝 Очистка логов (если есть)...
python -c "import os; logs = [f for f in os.listdir('.') if f.endswith('.log')]; [os.remove(f) for f in logs]; print(f'   ✅ Удалено {len(logs)} лог-файлов') if logs else print('   ℹ️ Лог-файлы не найдены')"

echo.
echo ✨ Очистка проекта завершена!
pause