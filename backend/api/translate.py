# api/translate.py — Paragraph / Long-text Translation (LCEL only)
#
# LCEL chain (agents_lcel) 为唯一路径。术语/TM/RAG 由工具预注入 prompt。
# 共享 _preprocess_translate（TM 精确匹配 + provider 配置）和 _postprocess_translation。

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

from agents_lcel.postprocess import get_cleaner
from models.schemas import TranslateRequest
from model_providers import LLMManager, ProviderNotConfiguredError
from services.model_router import model_router
from services.translation_memory import tm_instance
from services.memory_bank_manager import memory_bank_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# 预处理（TM 精确匹配检查 + 模型路由 + provider 配置）
# ---------------------------------------------------------------------------
async def _preprocess_translate(req: TranslateRequest):
    """翻译请求的预处理：TM 精确命中检查 + 路由解析 + provider 配置。

    Returns:
        dict with keys: tm_hit(bool), tm_translation(str|None),
        task(str), route(dict), memory, terms(dict),
        has_book(bool), book_title(str), llm(LLMManager), gen_kwargs(dict)
    """
    task_name = req.task
    route = model_router.resolve_provider(task_name, None if req.provider == "auto" else req.provider)

    book_title = (req.book_title or "").strip()
    has_book = bool(book_title)
    memory = memory_bank_manager.get_bank(book_title if has_book else None)

    # TM 精确匹配
    tm_translation = None
    if req.use_tm:
        exact = tm_instance.search_exact(req.text)
        if exact:
            tm_translation = exact["target"]

    terms = memory.get_terminology()

    # 确保 provider 已配置（关键副作用：首次调用时加载本地模型）
    llm = LLMManager()
    if not llm.get_provider("translate"):
        if route["provider"] == "local":
            from model_providers import ModelLoadConfig, LLMConfig
            llm.configure_local(
                route["model"],
                task="translate",
                load_config=ModelLoadConfig(load_in_4bit=True if route.get("quant") == "4bit" else False,
                                            load_in_8bit=True if route.get("quant") == "8bit" else False),
                llm_config=LLMConfig(temperature=route["temperature"], max_tokens=route["max_tokens"])
            )

    gen_kwargs = model_router.get_generation_kwargs(task_name)

    return {
        "tm_hit": tm_translation is not None,
        "tm_translation": tm_translation,
        "task": task_name,
        "route": route,
        "memory": memory,
        "terms": terms,
        "has_book": has_book,
        "book_title": book_title,
        "llm": llm,
        "gen_kwargs": gen_kwargs,
    }


# ---------------------------------------------------------------------------
# 后处理
# ---------------------------------------------------------------------------
def _postprocess_translation(req: TranslateRequest, pre: dict, raw: str) -> tuple:
    """清洗 LLM 输出 + 写入 memory bank + 写入 TM。

    Returns:
        (translation, added) — 清洗后的译文 + memory bank 新增条数
    """
    translation = get_cleaner(pre["task"])(raw)
    added = pre["memory"].auto_build_from_translation(req.text, translation) if pre["has_book"] else 0
    if req.use_tm:
        tm_instance.add(req.text, translation)
    return translation, added


# ---------------------------------------------------------------------------
# LCEL 链构建
# ---------------------------------------------------------------------------
def _build_lcel_chain(req: TranslateRequest, pre: dict):
    """构建翻译 LCEL chain：术语/TM/RAG 预注入 prompt → LLM 生成。"""
    from agents_lcel.chains import build_translate_runnable

    route = pre["route"]
    return build_translate_runnable(
        task=req.task,
        source_text=req.text,
        book_title=pre["book_title"],
        kb_ids=req.kb_ids if req.use_rag else None,
        group=req.group_id or "",
        chapter=req.chapter or "",
        use_tm=req.use_tm,
        use_rag=req.use_rag,
        model_name=route.get("model", ""),
        extra_prompt_kwargs={},
    )


def _format_llm_error(err: Exception) -> str:
    """把常见 LLM 异常转为用户友好的中文错误消息。"""
    msg = str(err)
    if "token_type_ids" in msg:
        return "模型不支持当前分词器配置 (token_type_ids 不兼容)，请尝试更换模型。"
    if "out of memory" in msg.lower():
        return "显存不足，请缩短输入文本或使用更小的模型。"
    if "未配置" in msg or "not configured" in msg.lower():
        return "翻译模型未配置。请在设置中选择并保存模型。"
    return f"翻译生成失败: {msg[:200]}"


# ---------------------------------------------------------------------------
# SSE 工具
# ---------------------------------------------------------------------------
def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# 流式 SSE 生成器
# ---------------------------------------------------------------------------
async def _stream_generator(
    req: TranslateRequest, pre: dict
) -> AsyncGenerator[str, None]:
    """LCEL chain.astream() → token 事件 → done 事件。"""
    try:
        chain = _build_lcel_chain(req, pre)
    except Exception as e:
        logger.error("LCEL chain build failed: %s", e)
        yield _sse_event({"type": "error", "error": f"构建翻译链失败: {str(e)[:200]}"})
        return

    full = ""
    try:
        async for chunk in chain.astream({"input": req.text}):
            text = chunk if isinstance(chunk, str) else str(chunk or "")
            if text:
                full += text
                yield _sse_event({"type": "token", "text": text})
    except Exception as e:
        yield _sse_event({"type": "error", "error": _format_llm_error(e)})
        return

    # 后处理
    try:
        translation, added = _postprocess_translation(req, pre, full)
    except Exception as e:
        yield _sse_event({"type": "error", "error": f"后处理失败: {str(e)[:200]}"})
        return

    yield _sse_event({
        "type": "done",
        "success": True,
        "translation": translation,
        "task": pre["task"],
        "provider": pre["route"]["provider"],
        "model": pre["route"]["model"],
        "memory_terms": len(pre["terms"]),
        "memory_added": added,
        "book_title": pre["book_title"] or None,
        "engine": "lcel",
    })


# ---------------------------------------------------------------------------
# 非流式翻译端点
# ---------------------------------------------------------------------------
@router.post("/api/translate")
async def translate(req: TranslateRequest):
    """非流式翻译端点"""
    try:
        pre = await _preprocess_translate(req)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    # TM 精确命中直接返回
    if pre["tm_hit"]:
        return {"success": True, "translation": pre["tm_translation"], "from_tm": True}

    try:
        chain = _build_lcel_chain(req, pre)
        raw = await chain.ainvoke({"input": req.text})
        translation, added = _postprocess_translation(req, pre, raw)
        return {
            "success": True,
            "translation": translation,
            "task": pre["task"],
            "provider": pre["route"]["provider"],
            "model": pre["route"]["model"],
            "memory_terms": len(pre["terms"]),
            "memory_added": added,
            "book_title": pre["book_title"] or None,
            "engine": "lcel",
        }
    except ProviderNotConfiguredError:
        return JSONResponse(status_code=400, content={
            "success": False,
            "error": "翻译模型未配置。请在设置中选择并保存模型，或先在训练页面训练一个模型后点击「用于翻译」。",
        })
    except Exception as e:
        return {"success": False, "error": _format_llm_error(e)}


# ---------------------------------------------------------------------------
# 流式翻译端点
# ---------------------------------------------------------------------------
@router.post("/api/translate/stream")
async def translate_stream(req: TranslateRequest):
    """流式翻译端点 — SSE (text/event-stream)

    事件类型:
      - {"type":"token","text":"..."}         增量文本
      - {"type":"done", ...full payload...}   生成结束 + 后处理完成
      - {"type":"error","error":"..."}        失败
    """
    try:
        pre = await _preprocess_translate(req)
    except ValueError as e:
        async def err_gen():
            yield _sse_event({"type": "error", "error": str(e)})
        return StreamingResponse(err_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # TM 精确命中：直接推送 done 事件
    if pre["tm_hit"]:
        async def tm_gen():
            yield _sse_event({
                "type": "done",
                "success": True,
                "from_tm": True,
                "translation": pre["tm_translation"],
                "task": pre["task"],
                "provider": pre["route"]["provider"],
                "model": pre["route"]["model"],
                "memory_terms": len(pre["terms"]),
                "memory_added": 0,
                "book_title": pre["book_title"] or None,
            })
        return StreamingResponse(tm_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    gen = _stream_generator(req, pre)
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
