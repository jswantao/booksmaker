# app.py — 电子书翻译制作工作台 入口
# FastAPI 后端 API 服务。前端由 Next.js (frontend/) 独立提供。

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from config import Config, PROJECT_ROOT
from core.database import chroma_client
from services.translation_memory import tm_instance
from services.knowledge_manager import kb_manager
from services.embedding_service import sync_embedding_manager
from core.dependencies import sync_llm_manager
from services.knowledge_service import migrate_legacy_knowledge
from api import api_router


def create_app() -> FastAPI:
    """应用工厂：创建并配置 FastAPI 实例"""
    config = Config()
    Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(config.CHROMA_DB_PATH).mkdir(parents=True, exist_ok=True)
    Path(PROJECT_ROOT / "data").mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="电子书翻译制作工作台")

    # CORS: 允许 Next.js 前端 (localhost:3000) 访问 API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求体大小限制 (10MB)
    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > 10 * 1024 * 1024:
                    return JSONResponse(
                        {"success": False, "error": "请求体过大，最大允许10MB", "code": "PAYLOAD_TOO_LARGE"},
                        status_code=413,
                    )
            except ValueError:
                pass
        return await call_next(request)

    # 注册 API 路由
    app.include_router(api_router)

    # 初始化单例
    tm_instance.chroma_client = chroma_client
    kb_manager.chroma_client = chroma_client

    # 启动时同步管理器 + 迁移
    sync_embedding_manager()
    sync_llm_manager()
    migrate_legacy_knowledge()

    return app


# 模块级应用实例
app = create_app()


def main():
    """启动入口"""
    uvicorn.run(app, host="0.0.0.0", port=8008)


if __name__ == "__main__":
    main()

