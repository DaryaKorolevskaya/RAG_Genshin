"""LLM через LangChain. Все провайдеры OpenAI-совместимые, поэтому класс один — ChatOpenAI:
меняются только base_url, ключ и модель (см. PROVIDERS в config.py). Фолбэки — штатный .with_fallbacks()."""

from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from genshin_rag.config import Provider, load_providers

Role = Literal["main", "fast"]


def chat_model(provider: Provider, role: Role = "main") -> BaseChatModel:
    model = provider.fast_model if role == "fast" and provider.fast_model else provider.model
    return ChatOpenAI(
        model=model,
        base_url=provider.base_url,
        api_key=provider.api_key,
        temperature=0 if role == "fast" else provider.temperature,
        timeout=60,
        max_retries=provider.max_retries,  # повторы при 429 (лимит в минуту), потом — следующий провайдер
        stream_usage=False,  # не все OpenAI-совместимые API понимают stream_options
        reasoning_effort=provider.reasoning_effort,  # только для reasoning-моделей; None — не отправляется
        name=f"{provider.name}:{model}",
    )


def build_llm(role: Role = "main", providers: list[Provider] | None = None) -> Runnable:
    """Первый провайдер с ключом — основной, остальные — фолбэки по порядку."""
    providers = providers if providers is not None else load_providers()
    if not providers:
        raise RuntimeError("Нет ни одного LLM-провайдера с ключом: заполни .env "
                           "(см. .env.example и PROVIDERS в config.py)")
    models = [chat_model(p, role) for p in providers]
    return models[0].with_fallbacks(models[1:]) if len(models) > 1 else models[0]
