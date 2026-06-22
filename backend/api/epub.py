# api/epub.py — EPUB Replacement (LCEL only)
#
# 使用 build_chain_for_task("epub_replace") LCEL chain 为唯一路径。

import logging

from fastapi import APIRouter

from agents_lcel.postprocess import get_cleaner
from models.schemas import EpubReplaceRequest
from services.model_router import model_router

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/epub/replace")
async def replace_epub(req: EpubReplaceRequest):
    route = model_router.resolve_provider("epub_replace", None if req.provider == "auto" else req.provider)

    user_input = (
        f"新译文:\n{req.translation}\n\nEPUB代码:\n{req.epub_code}\n\n"
        f"请替换文本节点，保持标签不变，直接输出完整代码。"
    )

    from agents_lcel.chains import build_chain_for_task

    chain = build_chain_for_task(
        "epub_replace",
        model_name=route.get("model", ""),
        prompt_kwargs={"epub_constraints": ""},
    )
    raw = await chain.ainvoke({"input": user_input})
    out = get_cleaner("epub_replace")(raw)
    return {
        "success": True,
        "epub_code": out,
        "provider": route["provider"],
        "model": route["model"],
        "engine": "lcel",
    }
