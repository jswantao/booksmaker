# core/database.py — 数据库客户端初始化
# 模块职责：ChromaDB 持久化客户端 + SQLite 路径管理

import threading
from pathlib import Path
import sys
from types import ModuleType

# 终极拦截：通过注入伪 PostHog 模块，彻底根治 ChromaDB 发送 Telemetry 引起的 capture 参数报错
class DummyPostHog(ModuleType):
    def capture(self, *args, **kwargs): pass
    def Posthog(self, *args, **kwargs): return self

dummy_ph = DummyPostHog("posthoganalytics")
dummy_ph.Posthog = lambda *args, **kwargs: dummy_ph
dummy_ph.capture = lambda *args, **kwargs: None
sys.modules["posthoganalytics"] = dummy_ph
sys.modules["chromadb.telemetry.posthog"] = dummy_ph

import chromadb
from chromadb.config import Settings

# 彻底拦截并静默 ChromaDB 底层 telemetry 捕获报错日志
try:
    import chromadb.telemetry.product
    chromadb.telemetry.product.ProductTelemetry.capture = lambda self, *args, **kwargs: None
except Exception:
    pass
try:
    import chromadb.telemetry.core
    chromadb.telemetry.core.Telemetry.capture = lambda self, *args, **kwargs: None
except Exception:
    pass
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
