# config.py — 全局配置常量
# 模块职责：集中管理所有路径、默认值、环境变量初始化

import os

os.environ["ANONYMIZED_TELEMETRY"] = "False"

class Config:
    CHROMA_DB_PATH = "./chroma_db"
    UPLOAD_DIR = "./uploads"
    TM_DB_PATH = "./translation_memory.db"
    TM_COLLECTION = "translation_memory_vectors"
    KB_DB_PATH = "./kb_manager.db"

# ---- 用户 API 配置 ----
user_api_config = {
    "api_key": os.environ.get("OPENAI_API_KEY", ""),
    "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model_name": os.environ.get("OPENAI_MODEL", "gpt-4-turbo-preview"),
    "embedding_model": os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002"),
    "embedding_provider": os.environ.get("EMBEDDING_PROVIDER", "openai"),
    "bge_model_id": os.environ.get("BGE_MODEL_ID", "BAAI/bge-base-zh-v1.5"),
    # LLM 提供者配置
    "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),  # "openai" | "local"
    "local_translate_model": os.environ.get("LOCAL_TRANSLATE_MODEL", "Qwen/Qwen2-7B-Instruct"),
    "local_epub_model": os.environ.get("LOCAL_EPUB_MODEL", ""),  # 空 = 复用翻译模型
    "local_load_in_4bit": os.environ.get("LOCAL_LOAD_IN_4BIT", "true").lower() == "true",
    "local_load_in_8bit": os.environ.get("LOCAL_LOAD_IN_8BIT", "false").lower() == "true",
    # 模型下载源: "huggingface" (默认) | "modelscope" (魔搭社区，国内加速)
    "download_source": os.environ.get("DOWNLOAD_SOURCE", "huggingface"),
    "modelscope_cache_dir": os.environ.get("MODELSCOPE_CACHE_DIR", ""),
}

# ---- ebooklib 可用性 ----
try:
    from ebooklib import epub  # noqa: F401
    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False
    print("Warning: ebooklib not installed, EPUB file download unavailable. Run: pip install ebooklib")
