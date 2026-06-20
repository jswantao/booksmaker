# api/__init__.py — 主路由聚合
from fastapi import APIRouter
from api.config import router as config_router
from api.translate import router as translate_router
from api.epub import router as epub_router
from api.tm import router as tm_router
from api.knowledge import router as knowledge_router

api_router = APIRouter()
api_router.include_router(config_router)
api_router.include_router(translate_router)
api_router.include_router(epub_router)
api_router.include_router(tm_router)
api_router.include_router(knowledge_router)
