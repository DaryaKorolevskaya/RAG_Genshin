from dotenv import find_dotenv, load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(find_dotenv(usecwd=True))


class BotSettings(BaseSettings):
    telegram_bot_token: str | None = None
    telegram_proxy: str | None = None  # например socks5://127.0.0.1:1080 или http://127.0.0.1:8080
    rag_api_url: str = "http://127.0.0.1:8000"
    rag_timeout: float = 120  # граф может сделать несколько вызовов LLM подряд


settings = BotSettings()
