import os
import fitz
from loguru import logger
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
import config


def clean_extra_whitespace(text):
    return ' '.join(text.split())


def group_paragraphs(text):
    return text.replace("\n", " ").replace("\r", " ")


def load_pdf(files):
    if not isinstance(files, list):
        files = [files]
    
    documents = []
    for file_path in files:
        try:
            logger.info(f"Загрузка PDF: {file_path}")
            doc = fitz.open(file_path)
            text = ""
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                text += page.get_text("text")
            
            text = clean_extra_whitespace(text)
            text = group_paragraphs(text)
            
            document = Document(
                page_content=text,
                metadata={"source": file_path}
            )
            documents.append(document)
            logger.success(f"Успешно загружен: {file_path}")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки {file_path}: {e}")
            raise
    
    return documents


def chunk_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=config.SEPARATORS
    )
    
    chunks = splitter.split_documents(documents)
    analyze_chunk_quality(chunks)
    return chunks


def analyze_chunk_quality(chunks):
    if not chunks:
        return
    
    chunk_sizes = [len(chunk.page_content) for chunk in chunks]
    avg_size = sum(chunk_sizes) / len(chunk_sizes)
    
    logger.info("Статистика чанков:")
    logger.info(f"   • Общее количество: {len(chunks)}")
    logger.info(f"   • Средний размер: {avg_size:.0f} символов")
    logger.info(f"   • Минимальный: {min(chunk_sizes)}")
    logger.info(f"   • Максимальный: {max(chunk_sizes)}")
    
    good_chunks = [c for c in chunks if 200 < len(c.page_content) < 1500]
    quality_ratio = len(good_chunks) / len(chunks)
    
    logger.info(f"   • Качество: {quality_ratio:.1%} хороших чанков")