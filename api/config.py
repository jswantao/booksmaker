# api/config.py — API 配置端点
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from models.schemas import ApiConfigRequest, EmbeddingSwitchRequest
from config import user_api_config
from core.dependencies import ConfigError, sync_llm_manager
from model_providers import LLMManager
from services.embedding_service import sync_embedding_manager, get_embedding_status

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.post("/api/config")
async def set_config(req: ApiConfigRequest):
    global user_api_config
    # 保存环境变量驱动的配置（clear 前备份，避免丢失）
    _saved_4bit = user_api_config.get("local_load_in_4bit", True)
    _saved_8bit = user_api_config.get("local_load_in_8bit", False)
    # 使用 dict.update() 而非 = 重新绑定，保持跨模块引用一致性
    user_api_config.clear()
    user_api_config.update({
        "api_key": req.api_key, "base_url": req.base_url, "model_name": req.model_name,
        "embedding_model": req.embedding_model, "embedding_provider": req.embedding_provider,
        "bge_model_id": req.bge_model_id,
        "llm_provider": req.llm_provider,
        "local_translate_model": req.local_translate_model,
        "local_epub_model": req.local_epub_model,
        "local_load_in_4bit": _saved_4bit,
        "local_load_in_8bit": _saved_8bit,
    })

    sync_embedding_manager()
    sync_llm_manager()

    # 连接测试
    try:
        if req.llm_provider == "local":
            # 本地模式：触发后台异步模型加载
            LLMManager().preload_local_models()
            status = LLMManager().get_all_status()
            tasks = list(status.keys())
            if not tasks:
                return {"success": False, "error": "本地模型配置失败，请检查模型 ID", "code": "LOCAL_CONFIG_ERROR"}
            return {"success": True,
                    "message": f"本地模型已配置 ({len(tasks)} 个任务)，正在后台异步加载..."}
        else:
            LLMManager().chat([{"role": "user", "content": "test"}], task="default", max_tokens=5)
            return {"success": True, "message": "API配置成功，连接测试通过"}
    except ConfigError as e:
        return {"success": False, "error": str(e), "code": "API_KEY_MISSING"}
    except Exception as e:
        return {"success": False, "error": f"API配置失败：{str(e)}"}


@router.get("/api/config")
async def get_config():
    return {
        "api_key": "***" if user_api_config.get("api_key") else "",
        "base_url": user_api_config.get("base_url", ""),
        "model_name": user_api_config.get("model_name", ""),
        "embedding_model": user_api_config.get("embedding_model", ""),
        "embedding_provider": user_api_config.get("embedding_provider", "openai"),
        "bge_model_id": user_api_config.get("bge_model_id", "BAAI/bge-base-zh-v1.5"),
        "llm_provider": user_api_config.get("llm_provider", "openai"),
        "local_translate_model": user_api_config.get("local_translate_model", ""),
        "local_epub_model": user_api_config.get("local_epub_model", ""),
        "is_configured": bool(user_api_config.get("api_key") or user_api_config.get("llm_provider") == "local")
    }


@router.get("/api/config/llm/status")
async def get_llm_status():
    """返回本地 LLM 模型加载状态"""
    return {"success": True, "status": LLMManager().get_all_status()}


@router.get("/api/config/embedding/status")
async def embedding_status():
    return get_embedding_status()


@router.post("/api/config/embedding")
async def switch_embedding(req: EmbeddingSwitchRequest):
    global user_api_config
    if req.provider not in ("openai", "bge"):
        return {"success": False, "error": "无效的提供者，仅支持 'openai' 或 'bge'"}
    user_api_config["embedding_provider"] = req.provider
    if req.embedding_model: user_api_config["embedding_model"] = req.embedding_model
    if req.bge_model_id: user_api_config["bge_model_id"] = req.bge_model_id
    sync_embedding_manager()
    return {
        "success": True, "provider": req.provider,
        "warning": "嵌入提供者已切换。建议前往翻译记忆库管理面板执行「重建向量索引」以保持一致。"
    }
