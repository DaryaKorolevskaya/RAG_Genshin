import os
import sys
from loguru import logger
import telegram_bot


def setup_logging():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "bot.log",
        rotation="10 MB",
        retention="10 days",
        level="DEBUG"
    )


def check_environment():
    required_vars = ["TELEGRAM_BOT_TOKEN", "GEMINI_API_KEY"]
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Отсутствуют переменные окружения: {', '.join(missing_vars)}")
        return False
    
    return True


def main():
    setup_logging()
    logger.info("🚀 Запуск Genshin Impact RAG бота...")
    
    # Проверка окружения
    if not check_environment():
        sys.exit(1)
    
    try:
        # Запуск бота
        telegram_bot.run_bot()
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()