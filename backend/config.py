# config.py — v3 optimized
# 此文件在导入链最前端执行，锁定所有缓存/模型路径到项目目录
import os
from pathlib import Path

os.environ["ANONYMIZED_TELEMETRY"] = "False"

# 项目根目录 (backend/ 的父目录)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 模型缓存目录 (与 backend/models/ Python 包区分，用 model_cache)
MODELS_CACHE_DIR = str(PROJECT_ROOT / "model_cache")
# 合并模型输出目录 (LoRA 合并后的完整模型)
MERGED_MODELS_DIR = str(PROJECT_ROOT / "model_cache" / "merged")
# 旧版合并模型目录 (向后兼容，逐步迁移)
LEGACY_MODELS_DIR = str(PROJECT_ROOT / "models")

# ============================================================
# 锁定所有模型/缓存到项目目录，避免数据泄露到系统路径
# ============================================================
# HuggingFace 缓存 (默认 ~/.cache/huggingface)
os.environ.setdefault("HF_HOME", str(PROJECT_ROOT / "model_cache" / ".hf"))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(PROJECT_ROOT / "model_cache" / ".hf" / "hub"))
# ModelScope 缓存 (默认 ~/.cache/modelscope)
os.environ.setdefault("MODELSCOPE_CACHE_DIR", str(PROJECT_ROOT / "model_cache" / ".ms"))
# PyTorch 缓存 (默认 ~/.cache/torch)
os.environ.setdefault("TORCH_HOME", str(PROJECT_ROOT / "model_cache" / ".torch"))
# Transformers 缓存
os.environ.setdefault("TRANSFORMERS_CACHE", str(PROJECT_ROOT / "model_cache" / ".hf" / "transformers"))
# 国内镜像加速 (如已设置则保留用户值)
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 确保缓存目录存在
Path(MODELS_CACHE_DIR).mkdir(parents=True, exist_ok=True)
Path(MERGED_MODELS_DIR).mkdir(parents=True, exist_ok=True)

class Config:
    CHROMA_DB_PATH = str(PROJECT_ROOT / "chroma_db")
    UPLOAD_DIR = str(PROJECT_ROOT / "uploads")
    TM_DB_PATH = str(PROJECT_ROOT / "data" / "translation_memory.db")
    TM_COLLECTION = "translation_memory_vectors"
    KB_DB_PATH = str(PROJECT_ROOT / "data" / "kb_manager.db")

user_api_config = {
    "api_key": os.environ.get("OPENAI_API_KEY", ""),
    "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    "model_name": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
    "embedding_model": os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
    "embedding_provider": os.environ.get("EMBEDDING_PROVIDER", "openai"),
    "bge_model_id": os.environ.get("BGE_MODEL_ID", "BAAI/bge-base-zh-v1.5"),
    "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
    "local_translate_model": os.environ.get("LOCAL_TRANSLATE_MODEL", "Qwen/Qwen2-7B-Instruct"),
    "local_epub_model": os.environ.get("LOCAL_EPUB_MODEL", ""),
    "local_load_in_4bit": os.environ.get("LOCAL_LOAD_IN_4BIT", "true").lower() == "true",
    "local_load_in_8bit": os.environ.get("LOCAL_LOAD_IN_8BIT", "false").lower() == "true",
    "download_source": os.environ.get("DOWNLOAD_SOURCE", "huggingface"),
    "modelscope_cache_dir": MODELS_CACHE_DIR + "/.ms",
}

try:
    from ebooklib import epub  # noqa
    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False
