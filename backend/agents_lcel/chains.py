# agents_lcel/chains.py — LCEL chain 构建器
#
# 为 4 种任务（paragraph_translate / epub_replace / kb_build / long_text_translate）
# 构造 LangChain Runnable。默认走 "prompt 注入" 路径（把工具查询结果预先填进
# system prompt），兼容所有模型。对于支持 function calling 的模型，可在
# Phase 2 后续迭代中叠加 bind_tools 路径（本期默认关闭，避免 SSE 流式被破坏）。

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable

from agents_lcel.prompts import get_prompt_for_task
from agents_lcel.tools import (
    query_knowledge_base,
    query_terminology,
    query_translation_memory,
)
from langchain_adapters.factory import get_chat_model
from observability.callbacks import get_langchain_callbacks
from services.model_capabilities import supports_tool_calling

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 预查询：把工具结果直接拼成 prompt 片段，注入到 system/human message 里
# ---------------------------------------------------------------------------
def prequery_context_for_injection(
    *,
    source_text: str,
    book_title: str = "",
    kb_ids: Optional[List[str]] = None,
    group: str = "",
    chapter: str = "",
    use_tm: bool = True,
    use_rag: bool = True,
) -> str:
    """同步运行工具，把结果格式化为可注入 prompt 的字符串。

    用于 prompt 注入路径（默认）。即使工具失败也返回空串，不影响主链路。
    """
    parts: List[str] = []

    # 术语查询
    try:
        terms = query_terminology.invoke({"term": source_text[:200], "book_title": book_title or ""})
        if terms:
            parts.append(f"[术语参考]\n{terms}")
    except Exception as e:
        logger.debug("query_terminology pre-query failed: %s", e)

    # TM 模糊匹配
    if use_tm:
        try:
            tm = query_translation_memory.invoke({"source_text": source_text[:400], "top_k": 2})
            if tm:
                parts.append(f"[历史翻译参考]\n{tm}")
        except Exception as e:
            logger.debug("query_translation_memory pre-query failed: %s", e)

    # KB 混合检索
    if use_rag and kb_ids:
        try:
            import json
            rag = query_knowledge_base.invoke({
                "query": source_text[:300],
                "kb_ids_json": json.dumps(kb_ids),
                "group": group or "",
                "chapter": chapter or "",
            })
            if rag:
                parts.append(f"[知识库参考]\n{rag}")
        except Exception as e:
            logger.debug("query_knowledge_base pre-query failed: %s", e)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Chain 构建
# ---------------------------------------------------------------------------
def _filter_kwargs_for_prompt(prompt, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """按 prompt 声明的 input_variables 过滤 kwargs，避免 'missing variable' 报错。"""
    wanted = set(prompt.input_variables)
    # optional 占位符（MessagesPlaceholder）不在此列，单独处理
    wanted.update(getattr(prompt, "optional_variables", []) or [])
    return {k: v for k, v in kwargs.items() if k in wanted}


def build_chain_for_task(
    task: str,
    *,
    use_tools: bool = False,
    model_name: str = "",
    prompt_kwargs: Optional[Dict[str, Any]] = None,
) -> Runnable:
    """根据 task 构造 LCEL chain。

    Args:
        task: paragraph_translate / epub_replace / kb_build / long_text_translate 等
        use_tools: 是否启用 bind_tools 路径（需 model_name 支持 function calling）。
                   默认 False，走 prompt 注入。
        model_name: 用于判断 tool-calling 支持度；不填则按 ChatQoderWork.task 推断。
        prompt_kwargs: 要预先填进 prompt 的变量，如 dynamic_terms / context_summary /
                       epub_constraints / context_messages。缺省用空字符串填充。

    Returns:
        Runnable，输入 {"input": "..."}，输出 str。
    """
    prompt = get_prompt_for_task(task)
    chat = get_chat_model(task=task, model_name=model_name or None)

    # 填充缺省占位符，避免模板渲染时抛 KeyError
    defaults: Dict[str, Any] = {
        "dynamic_terms": "(无术语)",
        "context_summary": "",
        "epub_constraints": "",
        "context_messages": [],
    }
    if prompt_kwargs:
        defaults.update(prompt_kwargs)
    filled_kwargs = _filter_kwargs_for_prompt(prompt, defaults)

    partial_prompt = prompt.partial(**filled_kwargs)

    # tool-calling 路径（仅在模型支持且 use_tools=True 时启用）
    if use_tools and supports_tool_calling(model_name or chat.model_name):
        try:
            from langchain.agents import create_tool_calling_agent, AgentExecutor
            from agents_lcel.tools import ALL_TRANSLATION_TOOLS

            bound_model = chat.bind_tools(ALL_TRANSLATION_TOOLS)
            agent = create_tool_calling_agent(bound_model, ALL_TRANSLATION_TOOLS, partial_prompt)
            agent_chain = AgentExecutor(
                agent=agent,
                tools=ALL_TRANSLATION_TOOLS,
                verbose=False,
                return_intermediate_steps=False,
            ) | (lambda out: out.get("output", ""))
            return agent_chain.with_config({"callbacks": get_langchain_callbacks()})
        except Exception as e:
            logger.warning("tool-calling agent build failed, fallback to direct chain: %s", e)

    # 默认路径：直接 prompt → model → parser
    chain = partial_prompt | chat | StrOutputParser()
    # Auto-attach LangChain callbacks for observability (logs/langchain.log)
    return chain.with_config({"callbacks": get_langchain_callbacks()})


# ---------------------------------------------------------------------------
# 翻译专用便利函数：集成 pre-query + chain 构造
# ---------------------------------------------------------------------------
def build_translate_runnable(
    *,
    task: str = "paragraph_translate",
    source_text: str,
    book_title: str = "",
    kb_ids: Optional[List[str]] = None,
    group: str = "",
    chapter: str = "",
    use_tm: bool = True,
    use_rag: bool = True,
    model_name: str = "",
    extra_prompt_kwargs: Optional[Dict[str, Any]] = None,
) -> Runnable:
    """构造翻译 runnable：先 pre-query 工具 → 把结果注入 prompt → 调 LLM。"""
    injected = prequery_context_for_injection(
        source_text=source_text,
        book_title=book_title,
        kb_ids=kb_ids,
        group=group,
        chapter=chapter,
        use_tm=use_tm,
        use_rag=use_rag,
    )

    prompt_kwargs: Dict[str, Any] = extra_prompt_kwargs or {}
    if injected:
        # 把注入内容拼到 epub_constraints（翻译 prompt 里的占位符）
        existing = prompt_kwargs.get("epub_constraints", "")
        prompt_kwargs["epub_constraints"] = (existing + "\n\n" + injected).strip()

    return build_chain_for_task(
        task=task,
        use_tools=False,  # 默认关闭 tool-calling 路径，SSE 流式安全
        model_name=model_name,
        prompt_kwargs=prompt_kwargs,
    )
