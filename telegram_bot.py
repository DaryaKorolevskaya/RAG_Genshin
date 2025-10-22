import os
from loguru import logger
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import rag_pipeline
import config


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = """
🤖 Добро пожаловать в Genshin Impact RAG бот!

Я могу ответить на вопросы по лору Genshin Impact на основе статей сообщества Genshin Impact Lore.

Примеры вопросов:
• Расскажи о героях Каэнри'ах
• Кто такой Шиукоатль?
"""
    await update.message.reply_text(welcome_text)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /status"""
    status = rag_pipeline.get_status()
    status_text = "✅ Бот работает нормально" if status["initialized"] else "❌ Бот не инициализирован"
    
    details = f"""
Статус бота: {status_text}

Детали:
• Векторная БД: {'✅' if status['vectorstore_loaded'] else '❌'}
• Языковая модель: {'✅' if status['llm_loaded'] else '❌'}
"""
    await update.message.reply_text(details)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.effective_user.id
    
    logger.info(f"Вопрос от пользователя {user_id}: {user_message}")
    
    await update.message.chat.send_action(action="typing")
    
    try:
        response = rag_pipeline.ask_question(user_message)
        
        await update.message.reply_text(response)
        logger.success(f"Ответ сгенерирован {user_id}")
        
    except Exception as e:
        error_message = "Извините, произошла ошибка при обработке вашего вопроса."
        await update.message.reply_text(error_message)
        logger.error(f"Ошибка при обработке сообщения: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка в боте: {context.error}")


def initialize_bot():
    logger.info("Инициализация RAG пайплайна...")
    rag_pipeline.initialize()


def run_bot():
    logger.info("Запуск Telegram бота...")
    
    try:
        initialize_bot()
    except Exception as e:
        logger.error(f"Ошибка инициализации пайплайна: {e}")
        return
    
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.success("✅ Бот запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)