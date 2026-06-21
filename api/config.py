# api/config.py — Config endpoints v3
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from models.schemas import ApiConfigRequest
from config import user_api_config
from core.dependencies import sync_llm_manager
from model_providers import LLMManager
from services.embedding_service import sync_embedding_manager

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/api/config")
async def set_config(req: ApiConfigRequest):
    user_api_config.update(req.model_dump())
    sync_embedding_manager()
    sync_llm_manager()
    return {"success": True, "message": "配置已保存", "provider": user_api_config.get("llm_provider")}

@router.get("/api/config")
async def get_config():
    c = user_api_config.copy()
    if c.get("api_key"): c["api_key"] = "***"
    c["is_configured"] = bool(user_api_config.get("api_key") or user_api_config.get("llm_provider") == "local")
    return c

@router.get("/api/config/llm/status")
async def get_llm_status():
    return {"success": True, "status": LLMManager().get_all_status()}
