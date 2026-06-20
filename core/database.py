# core/database.py — 数据库客户端初始化
# 模块职责：ChromaDB 持久化客户端 + SQLite 路径管理

import threading
from pathlib import Path
import chromadb
from chromadb.config import Settings
from config import Config

config = Config()
Path(config.UPLOAD_DIR).mkdir(exist_ok=True)
Path(config.CHROMA_DB_PATH).mkdir(exist_ok=True)

# ChromaDB 客户端（允许重置以处理版本迁移）
chroma_client = chromadb.PersistentClient(
    path=config.CHROMA_DB_PATH,
    settings=Settings(anonymized_telemetry=False, allow_reset=True)
)

# ChromaDB 迁移锁（保护 get_collection 的 reset 操作）
_chroma_migration_lock = threading.Lock()
