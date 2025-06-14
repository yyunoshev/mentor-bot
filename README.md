# 🐳 AI Telegram Bot - Docker Setup

## 📁 Структура проекта

```
ai_telegram_bot/
├── Dockerfile
├── docker-compose.yml
├── main.py
├── requirements.txt
├── mongo-init.js
├── .env
├── .env.example
├── logs/
└── README.md
```

## 🚀 Быстрый запуск

### 1. Клонирование и подготовка

```bash
# Создайте директорию проекта
mkdir ai_telegram_bot
cd ai_telegram_bot

# Скопируйте все файлы из артефактов
# Создайте директорию для логов
mkdir logs
```

### 2. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
# ОБЯЗАТЕЛЬНО заполните эти переменные!
BOT_TOKEN=ваш_telegram_bot_token
OPENAI_API_KEY=ваш_openai_api_key
```

**Как получить токены:**
- **Telegram Bot Token**: Напишите @BotFather в Telegram → /newbot
- **OpenAI API Key**: https://platform.openai.com/api-keys

### 3. Запуск

```bash
# Обычный запуск
docker-compose up -d

# С выводом логов
docker-compose up

# Запуск с MongoDB Express (веб-интерфейс для базы данных)
docker-compose --profile tools up -d
```

## 📊 Мониторинг

### Логи бота
```bash
# Просмотр логов
docker-compose logs ai_bot

# Следить за логами в реальном времени
docker-compose logs -f ai_bot
```

### MongoDB Express (опционально)
Если запустили с профилем `tools`, то веб-интерфейс доступен по адресу:
- **URL**: http://localhost:8081
- **Логин**: admin
- **Пароль**: admin123

### Статус контейнеров
```bash
# Проверить статус
docker-compose ps

# Перезапустить бота
docker-compose restart ai_bot
```

## 🛠 Управление

### Остановка
```bash
# Остановить все контейнеры
docker-compose down

# Остановить и удалить данные
docker-compose down -v
```

### Обновление кода
```bash
# Пересобрать образ после изменения кода
docker-compose build ai_bot

# Перезапустить с новым кодом
docker-compose up -d --build ai_bot
```

## 🔧 Конфигурация

### Переменные окружения

| Переменная | Описание | Значение по умолчанию |
|------------|----------|----------------------|
| `BOT_TOKEN` | Токен Telegram бота