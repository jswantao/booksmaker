# api/epub.py — EPUB Replacement v3
from fastapi import APIRouter
from models.schemas import EpubReplaceRequest
from agents import get_agent_by_task
from model_providers import LLMManager
from services.model_router import model_router

router = APIRouter()

@router.post("/api/epub/replace")
async def replace_epub(req: EpubReplaceRequest):
    route = model_router.resolve_provider("epub_replace", None if req.provider=="auto" else req.provider)
    agent = get_agent_by_task("epub_replace")
    if agent is None:
        return {"success": False, "error": "EPUB替换Agent未找到"}
    sys_prompt = agent.build_system_prompt()
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"新译文:\n{req.translation}\n\nEPUB代码:\n{req.epub_code}\n\n请替换文本节点，保持标签不变，直接输出完整代码。"}
    ]
    llm = LLMManager()
    gen_kwargs = model_router.get_generation_kwargs("epub_replace")
    try:
        out = llm.chat(messages, task="epub", **gen_kwargs)
    except Exception:
        out = llm.chat(messages, task="default", **gen_kwargs)
    out = agent.process_response(out)
    return {"success": True, "epub_code": out, "provider": route["provider"], "model": route["model"]}
