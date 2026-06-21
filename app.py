# app.py — 智能翻译与EPUB工作台 入口
# 应用工厂：创建 FastAPI 实例、挂载静态文件、注册路由、启动初始化

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from config import Config
from core.database import chroma_client
from services.translation_memory import tm_instance
from services.knowledge_manager import kb_manager
from services.embedding_service import sync_embedding_manager
from core.dependencies import sync_llm_manager
from services.knowledge_service import migrate_legacy_knowledge
from api import api_router

# ---- 配置 ----
config = Config()
Path(config.UPLOAD_DIR).mkdir(exist_ok=True)
Path(config.CHROMA_DB_PATH).mkdir(exist_ok=True)

# ---- FastAPI 应用 ----
app = FastAPI(title="智能翻译与EPUB工作台")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---- 中间件 ----
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > 10 * 1024 * 1024:
                return JSONResponse(
                    {"success": False, "error": "请求体过大，最大允许10MB", "code": "PAYLOAD_TOO_LARGE"},
                    status_code=413)
        except ValueError:
            pass
    return await call_next(request)


# ---- 注册路由 ----
app.include_router(api_router)


# ---- 初始化单例 ----
def _init_singletons():
    """将 chroma_client 注入到服务单例中"""
    tm_instance.chroma_client = chroma_client
    kb_manager.chroma_client = chroma_client


_init_singletons()

# 启动时同步管理器 + 迁移
sync_embedding_manager()
sync_llm_manager()
migrate_legacy_knowledge()


# ---- 启动入口 ----
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8008)
