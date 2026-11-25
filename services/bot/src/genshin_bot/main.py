"""Telegram-бот «Артерии земли»: принимает сообщение, спрашивает RAG-сервис, присылает ответ и источники.
История диалога хранится в сервисе по thread_id = tg:<chat_id>."""

import asyncio

import httpx
from loguru import logger
from telegram import LinkPreviewOptions, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import NetworkError, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from genshin_bot.client import RagClient
from genshin_bot.config import settings
from genshin_bot.formatting import format_sources, md_to_tg_html, split_message

START_TEXT = (
    "✦ <b>Артерии земли</b>\n\n"
    "Артерии земли хранят память Тейвата. Отвечаю на вопросы по лору Genshin Impact "
    "по статьям канала Genshin Impact Lore и даю ссылки на источники.\n\n"
    "Например:\n• Кто такие шесть героев Каэнри'ах?\n• Кем на самом деле является Царица?\n\n"
    "/reset — начать разговор заново"
)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
SEND_ATTEMPTS = 3


def thread_id(update: Update) -> str:
    return f"tg:{update.effective_chat.id}"


def rag(context: ContextTypes.DEFAULT_TYPE) -> RagClient:
    return context.application.bot_data["rag"]


async def reply(message: Message, text: str, html: bool = True) -> None:
    """Отправка с повтором: связь с Telegram иногда пропадает на секунды, ответ терять не хотим."""
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            await message.reply_text(text, parse_mode=ParseMode.HTML if html else None,
                                     link_preview_options=NO_PREVIEW)
            return
        except (NetworkError, TimedOut) as e:
            if attempt == SEND_ATTEMPTS:
                raise
            logger.warning(f"Не удалось отправить ({e}), повтор {attempt}/{SEND_ATTEMPTS - 1}")
            await asyncio.sleep(2 * attempt)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update.message, START_TEXT)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await rag(context).reset(thread_id(update))
    await reply(update.message, "Начнём сначала ✦", html=False)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        answer = await rag(context).ask(update.message.text.strip(), thread_id(update))
    except httpx.HTTPError as e:
        logger.error(f"RAG-сервис не ответил: {e!r}")
        await reply(update.message, "Артерии земли молчат 😔 Попробуй ещё раз чуть позже.", html=False)
        return

    for part in split_message(answer.text):
        await reply(update.message, md_to_tg_html(part))
    if text := format_sources(answer.sources):
        await reply(update.message, text)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сетевые сбои — коротко в лог, остальное — с трейсбеком."""
    if isinstance(context.error, (NetworkError, TimedOut)):
        logger.warning(f"Сетевая ошибка Telegram: {context.error}")
    else:
        logger.opt(exception=context.error).error("Ошибка в обработчике")


async def post_init(app: Application) -> None:
    app.bot_data["rag"] = RagClient(settings.rag_api_url, settings.rag_timeout)
    logger.success(f"Бот запущен, RAG-сервис: {settings.rag_api_url}")


async def post_shutdown(app: Application) -> None:
    await app.bot_data["rag"].close()


def main() -> None:
    if not settings.telegram_bot_token:
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN в .env (получить у @BotFather)")
    builder = (Application.builder().token(settings.telegram_bot_token).concurrent_updates(True)
               .connect_timeout(20).read_timeout(30).write_timeout(30).pool_timeout(10)
               .get_updates_connect_timeout(20).get_updates_read_timeout(40)
               .post_init(post_init).post_shutdown(post_shutdown))
    if settings.telegram_proxy:  # если Telegram доступен только через прокси
        builder = builder.proxy(settings.telegram_proxy).get_updates_proxy(settings.telegram_proxy)
    app = builder.build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
