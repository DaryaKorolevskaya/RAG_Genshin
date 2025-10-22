from loguru import logger
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import config

# Глобальные переменные
llm = None
chain = None


def create_gemini_llm():
    """Создание Gemini LLM через LangChain"""
    global llm
    
    try:
        llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_MODEL,
            temperature=0.3,
            max_tokens=3000,
            google_api_key=config.GEMINI_API_KEY
        )
        logger.success(f"✅ Gemini модель загружена: {config.GEMINI_MODEL}")
        return llm
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки Gemini: {e}")
        return None


def create_prompt_template():
    """Создание промпт-шаблона"""
    template = """
Ты - эксперт по лору игры Genshin Impact. Ответь на вопрос пользователя на основе предоставленного контекста.

КОНТЕКСТ:
{context}

ВОПРОС:
{question}

ИНСТРУКЦИИ:
- Отвечай ТОЛЬКО на русском языке
- Используй информацию из предоставленного контекста
- Давай полный развернутый ответ
- Если в контексте нет информации, сообщи об этом

ОТВЕТ:
"""
    return ChatPromptTemplate.from_template(template)


def create_chain():
    """Создание цепочки для генерации ответов"""
    global chain
    
    if llm is None:
        create_gemini_llm()
    
    prompt = create_prompt_template()
    chain = prompt | llm | StrOutputParser()
    return chain


def generate_response(question, context):
    """Генерация ответа на основе вопроса и контекста"""
    global chain
    
    try:
        if chain is None:
            create_chain()
        
        # Преобразуем контекст в строку
        context_text = "\n\n".join([doc.page_content for doc in context])
        
        response = chain.invoke({
            "context": context_text,
            "question": question
        })
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Ошибка генерации ответа: {e}")
        return "Извините, произошла ошибка при генерации ответа."