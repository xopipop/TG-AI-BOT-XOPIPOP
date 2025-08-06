# Настройка переменных окружения на Render

## Проблема
Приложение не запускается на Render из-за отсутствия переменных окружения:
```
ValueError: Пожалуйста, установите переменную окружения TELEGRAM_BOT_TOKEN в файле .env
```

## Решение

### 1. Перейдите в панель управления Render
- Войдите в свой аккаунт на [render.com](https://render.com)
- Найдите ваш сервис `telegram-ai-bot`

### 2. Настройте переменные окружения
В разделе **Environment** добавьте следующие переменные:

#### TELEGRAM_BOT_TOKEN
- **Key**: `TELEGRAM_BOT_TOKEN`
- **Value**: Ваш токен Telegram бота (получите у @BotFather)

#### OPENROUTER_API_KEY
- **Key**: `OPENROUTER_API_KEY`
- **Value**: Ваш API ключ OpenRouter

### 3. Примеры значений
```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4. Сохраните изменения
- Нажмите **Save Changes**
- Render автоматически перезапустит приложение

### 5. Проверьте логи
После сохранения проверьте логи развертывания - ошибки должны исчезнуть.

## Примечание
Переменные `WEBHOOK_URL` и `PORT` уже настроены в `render.yaml` и не требуют ручной настройки.
