#!/bin/bash

# Скрипт для запуска бота в Docker

set -e  # Выход при ошибке

echo "🚀 Запуск Genshin Impact RAG бота в Docker..."

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo "💡 Создайте файл .env на основе .env.example и заполните ваши ключи"
    exit 1
fi

# Проверяем наличие docker-compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose не установлен!"
    echo "💡 Установите docker-compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Сборка и запуск
echo "📦 Сборка Docker образа..."
docker-compose build

echo "🐳 Запуск контейнера..."
docker-compose up -d

echo "✅ Бот запущен в фоновом режиме!"
echo "📋 Полезные команды:"
echo "   Просмотр логов: docker-compose logs -f"
echo "   Остановка: docker-compose down"
echo "   Перезапуск: docker-compose restart"
echo "   Статус: docker-compose ps"

# Показываем логи
echo ""
echo "📜 Последние логи:"
docker-compose logs --tail=50
