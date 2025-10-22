from loguru import logger
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
import config

embedding_model = None
vectorstore = None


def load_embedding_model():
    global embedding_model
    
    try:
        model_kwargs = {"device": "cpu"} 
        encode_kwargs = {"normalize_embeddings": True}
        
        embedding_model = HuggingFaceEmbeddings(
            model_name=config.EMBEDDING_MODEL,
            model_kwargs=model_kwargs,
            encode_kwargs=encode_kwargs,
        )
        
        logger.success(f"✅ Модель эмбеддингов загружена: {config.EMBEDDING_MODEL}")
        return embedding_model
        
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки модели: {e}")
        raise


def create_vectorstore(chunks):
    global vectorstore
    
    logger.info("Создание векторной базы данных...")
    
    if embedding_model is None:
        load_embedding_model()
    
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embedding_model,
        persist_directory=config.VECTORSTORE_PATH
    )
    
    logger.success("✅ Векторная база данных создана")
    return vectorstore


def load_vectorstore():
    global vectorstore
    
    logger.info("Загрузка векторной базы данных...")
    
    if embedding_model is None:
        load_embedding_model()
    
    vectorstore = Chroma(
        persist_directory=config.VECTORSTORE_PATH,
        embedding_function=embedding_model
    )
    
    logger.success("✅ Векторная база данных загружена")
    return vectorstore


def search_similar(query, k=None, filter_dict=None):
    if k is None:
        k = config.DEFAULT_K
    
    if vectorstore is None:
        raise ValueError("Векторная база данных не инициализирована")
    
    results = vectorstore.similarity_search(
        query=query,
        k=k,
        filter=filter_dict
    )
    
    logger.info(f"Найдено {len(results)} результатов для: '{query}'")
    return results


def retrieve_context(query, k=None):
    retrieved_docs = search_similar(query, k)
    return retrieved_docs
