from loguru import logger
import document_processor
import vector_store
import llm_manager
import config

is_initialized = False


def initialize(pdf_files=None):
    global is_initialized
    
    try:
        # Если указаны PDF файлы, создаем новую векторную БД
        if pdf_files:
            logger.info("Инициализация с новыми PDF файлами...")
            documents = document_processor.load_pdf(pdf_files)
            chunks = document_processor.chunk_documents(documents)
            vector_store.create_vectorstore(chunks)
        else:
            # Иначе загружаем существующую БД
            logger.info("Загрузка существующей векторной БД...")
            vector_store.load_vectorstore()
        
        llm_manager.create_chain()
        
        is_initialized = True
        logger.success("✅ RAG пайплайн инициализирован")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации RAG пайплайна: {e}")
        raise


def ask_question(question, k=None):
    if not is_initialized:
        raise ValueError("Пайплайн не инициализирован. Вызовите initialize() first.")
    
    try:
        # Получаем релевантный контекст
        context = vector_store.retrieve_context(question, k)
        
        # Генерируем ответ
        response = llm_manager.generate_response(question, context)
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке вопроса: {e}")
        return f"Произошла ошибка: {str(e)}"


def get_similar_chunks(query, k=None):
    if not is_initialized:
        raise ValueError("Пайплайн не инициализирован.")
    
    return vector_store.search_similar(query, k)


def get_status():
    return {
        "initialized": is_initialized,
        "vectorstore_loaded": vector_store.vectorstore is not None,
        "llm_loaded": llm_manager.llm is not None
    }