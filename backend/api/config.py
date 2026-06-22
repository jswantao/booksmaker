# api/config.py — Config endpoints v3
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Query
from models.schemas import ApiConfigRequest
from config import user_api_config
from core.dependencies import sync_llm_manager
from model_providers import LLMManager
from services.embedding_service import sync_embedding_manager
from embedding_providers import EmbeddingManager
from typing import Optional
import urllib.request
import json

router = APIRouter()
_model_loader_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-loader")

# ---- 根路径 ----

@router.get("/")
async def root():
    """API 服务健康检查。前端请访问 http://localhost:3000"""
    return {
        "service": "电子书翻译制作工作台 API",
        "version": "3.0",
        "docs": "/docs",
        "frontend": "http://localhost:3000",
        "endpoints": 42,
    }

# ---- 配置端点 ----

@router.post("/api/config")
async def set_config(req: ApiConfigRequest):
    user_api_config.update(req.model_dump())
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_model_loader_pool, _load_models_sync)
    return {"success": True, "message": "配置已保存", "provider": user_api_config.get("llm_provider")}


@router.patch("/api/config")
async def patch_config(req: ApiConfigRequest):
    """Partial update: only overwrites fields explicitly provided in the request body."""
    user_api_config.update(req.model_dump(exclude_unset=True))
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_model_loader_pool, _load_models_sync)
    return {"success": True, "message": "配置已更新", "provider": user_api_config.get("llm_provider")}


def _load_models_sync():
    """在线程池中同步配置嵌入和 LLM 模型，并预加载默认模型权重"""
    try:
        sync_embedding_manager()
    except Exception as e:
        print(f"[模型加载] 嵌入模型加载失败: {e}")
    try:
        sync_llm_manager()
    except Exception as e:
        print(f"[模型加载] LLM 配置失败: {e}")
    # 预加载默认模型权重（仅一个 provider，避免 6GB VRAM OOM）
    try:
        provider = LLMManager().get_provider("default")
        if (provider and hasattr(provider, '_ensure_model_loaded')
                and getattr(provider, 'load_status', None) != 'ready'):
            print(f"[预加载] 开始加载: {provider.model_name}")
            provider._ensure_model_loaded()
        elif provider and getattr(provider, 'load_status', None) == 'ready':
            print(f"[预加载] 模型已就绪，跳过: {provider.model_name}")
    except Exception as e:
        print(f"[预加载] 失败 (首次翻译时重试): {e}")

@router.get("/api/config")
async def get_config():
    c = user_api_config.copy()
    if c.get("api_key"): c["api_key"] = "***"
    c["is_configured"] = bool(user_api_config.get("api_key") or user_api_config.get("llm_provider") == "local")
    return c

@router.get("/api/config/llm/status")
async def get_llm_status():
    return {"success": True, "status": LLMManager().get_all_status()}

@router.get("/api/config/embedding/status")
async def get_embedding_status():
    try:
        mgr = EmbeddingManager()
        return {"success": True, "provider": mgr._provider_type if hasattr(mgr, '_provider_type') else "unknown",
                "loaded": mgr._model is not None if hasattr(mgr, '_model') else False}
    except Exception as e:
        return {"success": True, "provider": "unknown", "loaded": False, "error": str(e)}


# ==================== ModelScope 模型搜索 ====================

# 已知 ≤7B 的优质小模型列表（离线兜底）
_PRESET_SMALL_MODELS = [
    {"id": "Tencent-Hunyuan/Hy-MT2-1.8B", "name": "Hy-MT2-1.8B", "params": "1.8B", "family": "Hunyuan", "desc": "混元翻译二代，1.8B轻量，魔搭独占，微调首选"},
    {"id": "Tencent-Hunyuan/Hunyuan-MT-7B", "name": "Hunyuan-MT-7B", "params": "7B", "family": "Hunyuan", "desc": "混元翻译一代，7B，魔搭独占"},
    {"id": "Qwen/Qwen3.5-4B", "name": "Qwen3.5-4B", "params": "4B", "family": "Qwen", "desc": "通义千问3.5，4B最新版，推理+翻译强 ⭐新"},
    {"id": "Qwen/Qwen3.5-8B", "name": "Qwen3.5-8B", "params": "8B", "family": "Qwen", "desc": "通义千问3.5，8B最新版 ⚠超7B"},
    {"id": "Qwen/Qwen2.5-7B-Instruct", "name": "Qwen2.5-7B-Instruct", "params": "7B", "family": "Qwen", "desc": "通义千问2.5，7B指令版，综合能力强"},
    {"id": "Qwen/Qwen2.5-3B-Instruct", "name": "Qwen2.5-3B-Instruct", "params": "3B", "family": "Qwen", "desc": "阿里通义千问2.5，3B轻量指令版"},
    {"id": "Qwen/Qwen2.5-1.5B-Instruct", "name": "Qwen2.5-1.5B-Instruct", "params": "1.5B", "family": "Qwen", "desc": "阿里通义千问2.5，1.5B超轻量，CPU可用"},
    {"id": "Qwen/Qwen2.5-0.5B-Instruct", "name": "Qwen2.5-0.5B-Instruct", "params": "0.5B", "family": "Qwen", "desc": "阿里通义千问2.5，0.5B迷你版，CPU可用"},
    {"id": "Qwen/Qwen2-7B-Instruct", "name": "Qwen2-7B-Instruct", "params": "7B", "family": "Qwen", "desc": "阿里通义千问2，7B指令版（当前默认）"},
    {"id": "Qwen/Qwen2-1.5B-Instruct", "name": "Qwen2-1.5B-Instruct", "params": "1.5B", "family": "Qwen", "desc": "阿里通义千问2，1.5B指令版"},
    {"id": "THUDM/chatglm3-6b", "name": "ChatGLM3-6B", "params": "6B", "family": "ChatGLM", "desc": "智谱ChatGLM3，6B双语对话模型"},
    {"id": "THUDM/chatglm4-1.5b", "name": "ChatGLM4-1.5B", "params": "1.5B", "family": "ChatGLM", "desc": "智谱ChatGLM4，1.5B轻量版"},
    {"id": "google/gemma-2-2b-it", "name": "Gemma-2-2B-it", "params": "2B", "family": "Gemma", "desc": "Google Gemma 2，2B指令版"},
    {"id": "google/gemma-2-2b-jpn-it", "name": "Gemma-2-2B-JPN-it", "params": "2B", "family": "Gemma", "desc": "Google Gemma 2 日语特化，2B"},
    {"id": "mistralai/Mistral-7B-Instruct-v0.3", "name": "Mistral-7B-Instruct-v0.3", "params": "7B", "family": "Mistral", "desc": "Mistral AI，7B指令版v0.3"},
    {"id": "meta-llama/Llama-3.2-3B-Instruct", "name": "Llama-3.2-3B-Instruct", "params": "3B", "family": "Llama", "desc": "Meta Llama 3.2，3B指令版"},
    {"id": "meta-llama/Llama-3.2-1B-Instruct", "name": "Llama-3.2-1B-Instruct", "params": "1B", "family": "Llama", "desc": "Meta Llama 3.2，1B超轻量"},
    {"id": "microsoft/Phi-3-mini-4k-instruct", "name": "Phi-3-mini-4k", "params": "3.8B", "family": "Phi", "desc": "微软Phi-3 Mini，3.8B，推理强"},
    {"id": "internlm/internlm2-chat-7b", "name": "InternLM2-Chat-7B", "params": "7B", "family": "InternLM", "desc": "上海AI Lab书生·浦语2，7B"},
    {"id": "internlm/internlm2-chat-1_8b", "name": "InternLM2-Chat-1.8B", "params": "1.8B", "family": "InternLM", "desc": "上海AI Lab书生·浦语2，1.8B轻量"},
    {"id": "01-ai/Yi-1.5-6B-Chat", "name": "Yi-1.5-6B-Chat", "params": "6B", "family": "Yi", "desc": "零一万物Yi-1.5，6B对话版"},
    {"id": "deepseek-ai/deepseek-coder-6.7b-instruct", "name": "DeepSeek-Coder-6.7B", "params": "6.7B", "family": "DeepSeek", "desc": "DeepSeek Coder，6.7B代码指令版"},
    {"id": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "name": "DeepSeek-R1-Distill-Qwen-7B", "params": "7B", "family": "DeepSeek", "desc": "DeepSeek R1蒸馏版，7B推理增强"},
]

# HF ID → ModelScope ID 映射（用于检查 ModelScope 可用性）
_MODELSCOPE_ID_MAP = {
    "Qwen/Qwen3.5-4B": "qwen/Qwen3.5-4B",
    "Qwen/Qwen3.5-8B": "qwen/Qwen3.5-8B",
    "Qwen/Qwen2.5-7B-Instruct": "qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-3B-Instruct": "qwen/Qwen2.5-3B-Instruct",
    "Qwen/Qwen2.5-1.5B-Instruct": "qwen/Qwen2.5-1.5B-Instruct",
    "Qwen/Qwen2.5-0.5B-Instruct": "qwen/Qwen2.5-0.5B-Instruct",
    "Qwen/Qwen2-7B-Instruct": "qwen/Qwen2-7B-Instruct",
    "Qwen/Qwen2-1.5B-Instruct": "qwen/Qwen2-1.5B-Instruct",
    "THUDM/chatglm3-6b": "ZhipuAI/chatglm3-6b",
    "THUDM/chatglm4-1.5b": "ZhipuAI/chatglm4-1.5b",
    "internlm/internlm2-chat-7b": "Shanghai_AI_Laboratory/internlm2-chat-7b",
    "internlm/internlm2-chat-1_8b": "Shanghai_AI_Laboratory/internlm2-chat-1_8b",
    "deepseek-ai/deepseek-coder-6.7b-instruct": "deepseek-ai/deepseek-coder-6.7b-instruct",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "Tencent-Hunyuan/Hunyuan-MT-7B": "Tencent-Hunyuan/Hunyuan-MT-7B",
    "Tencent-Hunyuan/Hy-MT2-1.8B": "Tencent-Hunyuan/Hy-MT2-1.8B",
}


def _check_modelscope_available(model_id: str) -> bool:
    """快速检查模型在 ModelScope 上是否可用（HEAD 请求）"""
    ms_id = _MODELSCOPE_ID_MAP.get(model_id, model_id)
    try:
        url = f"https://www.modelscope.cn/api/v1/models/{ms_id}"
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "BookTranslator/1.0")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


@router.get("/api/modelscope/search")
async def search_modelscope_models(
    q: str = Query(default="", description="搜索关键词"),
    max_params: float = Query(default=7, description="最大参数量 (B)"),
):
    """
    搜索魔搭社区 ≤7B 的指令微调模型。

    优先使用 ModelScope API 在线搜索，网络异常时返回预设的精选小模型列表。
    返回每个模型的 HF ID、ModelScope 可用性、参数量等。
    """
    results = []

    # 尝试在线搜索 ModelScope API
    try:
        search_query = q.strip() or "instruct chat 7b"
        url = (
            "https://modelscope.cn/api/v1/models"
            f"?PageSize=30&PageNumber=1&SortBy=GmtModified"
            f"&Search={urllib.parse.quote(search_query)}"
            f"&Source= huggingface"
        )
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "BookTranslator/1.0")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("Data", {}).get("Models", []) if isinstance(data, dict) else []

        for item in items:
            name = item.get("Name", "")
            full_name = item.get("Path", "") or name
            desc = item.get("Description", "") or ""
            # 尝试提取参数量信息
            params_str = _extract_params(name + " " + desc)
            params_b = _parse_params_b(params_str)
            if params_b is not None and params_b > max_params:
                continue  # 超过参数量上限
            if params_b is None:
                params_b = 0
            # 只保留指令/对话模型
            name_lower = (name + desc).lower()
            if not any(kw in name_lower for kw in ("instruct", "chat", "对话", "指令", "qwen", "llama", "mistral", "gemma", "phi", "glm", "yi", "internlm", "deepseek")):
                continue

            results.append({
                "id": full_name,
                "name": name,
                "params": f"{params_b}B" if params_b > 0 else "?",
                "params_b": params_b,
                "family": _guess_family(full_name),
                "desc": desc[:120] if desc else "",
                "on_modelscope": True,
            })
    except Exception as e:
        pass  # 在线搜索失败，使用预设列表

    # 如果在线结果不足，使用预设列表兜底
    if len(results) < 3:
        for m in _PRESET_SMALL_MODELS:
            if m["id"] not in {r["id"] for r in results}:
                # 按搜索关键词过滤
                if q.strip():
                    kw = q.strip().lower()
                    if kw not in m["id"].lower() and kw not in m["desc"].lower() and kw not in m["family"].lower():
                        continue
                params_b = _parse_params_b(m["params"])
                if params_b is not None and params_b > max_params:
                    continue
                results.append({
                    "id": m["id"],
                    "name": m["name"],
                    "params": m["params"],
                    "params_b": params_b or 0,
                    "family": m["family"],
                    "desc": m["desc"],
                    "on_modelscope": m["id"] in _MODELSCOPE_ID_MAP,
                })

    # 按参数量排序（小→大）
    results.sort(key=lambda r: r.get("params_b", 0))

    # 标注 ModelScope 可用性（批量检查影响性能，改为按映射表判断）
    for r in results:
        r["on_modelscope"] = r["id"] in _MODELSCOPE_ID_MAP

    return {
        "success": True,
        "models": results,
        "count": len(results),
        "max_params": max_params,
        "preset_count": len(_PRESET_SMALL_MODELS),
    }


def _extract_params(text: str) -> str:
    """从文本中提取参数量字符串，如 '7B', '1.5B'"""
    import re
    m = re.search(r'(\d+\.?\d*)\s*[Bb]', text)
    return m.group(0) if m else ""


def _parse_params_b(params_str: str) -> Optional[float]:
    """解析参数量为浮点数，如 '7B' → 7.0, '1.5B' → 1.5"""
    import re
    m = re.search(r'(\d+\.?\d*)', str(params_str))
    return float(m.group(1)) if m else None


def _guess_family(model_id: str) -> str:
    """从模型 ID 猜测模型家族"""
    lid = model_id.lower()
    if "qwen" in lid: return "Qwen"
    if "chatglm" in lid or "glm" in lid: return "ChatGLM"
    if "llama" in lid: return "Llama"
    if "mistral" in lid: return "Mistral"
    if "gemma" in lid: return "Gemma"
    if "phi" in lid: return "Phi"
    if "yi" in lid: return "Yi"
    if "internlm" in lid: return "InternLM"
    if "deepseek" in lid: return "DeepSeek"
    if "hunyuan" in lid: return "Hunyuan"
    return "Other"
