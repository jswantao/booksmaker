# config.py — v3 optimized
import os
os.environ["ANONYMIZED_TELEMETRY"] = "False"

class Config:
    CHROMA_DB_PATH = "./chroma_db"
    UPLOAD_DIR = "./uploads"
    TM_DB_PATH = "./translation_memory.db"
    TM_COLLECTION = "translation_memory_vectors"
    KB_DB_PATH = "./kb_manager.db"

user_api_config = {
    "api_key": os.environ.get("OPENAI_API_KEY", ""),
    "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    # Cloud API Constraints: balance accuracy with token consumption
    "model_name": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),  # balanced tier default
    "embedding_model": os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    "embedding_provider": os.environ.get("EMBEDDING_PROVIDER", "openai"),
    "bge_model_id": os.environ.get("BGE_MODEL_ID", "BAAI/bge-base-zh-v1.5"),
    # Model Selection: Users can independently choose between locally deployed models or cloud API calls
    "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),  # "openai" | "local"
    # Local Model Constraints: Balance accuracy with hardware performance limitations
    "local_translate_model": os.environ.get("LOCAL_TRANSLATE_MODEL", "Qwen/Qwen2-7B-Instruct"),
    "local_epub_model": os.environ.get("LOCAL_EPUB_MODEL", ""),
    "local_load_in_4bit": os.environ.get("LOCAL_LOAD_IN_4BIT", "true").lower() == "true",
    "local_load_in_8bit": os.environ.get("LOCAL_LOAD_IN_8BIT", "false").lower() == "true",
    "download_source": os.environ.get("DOWNLOAD_SOURCE", "huggingface"),
    "modelscope_cache_dir": os.environ.get("MODELSCOPE_CACHE_DIR", ""),
}

try:
    from ebooklib import epub  # noqa
    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False
