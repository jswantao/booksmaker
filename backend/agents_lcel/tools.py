# agents_lcel/tools.py — LangChain @tool 定义
#
# 为翻译类 Agent 提供三个可被 bind_tools 绑定的工具：
#   - query_terminology   查 Memory Bank 术语 + 全局 terminology
#   - query_translation_memory  模糊查 TM（向量相似度）
#   - query_knowledge_base      跨 KB 混合检索
#
# 注意：这些工具既可以被 Agent Executor 通过 function calling 调用，
# 也可以被 chain 构造方直接调用（prompt 注入模式），所以参数都是
# 简单类型（str / int / JSON str），避免 LangChain schema 推断歧义。

from __future__ import annotations

import json
from typing import List, Optional

from langchain_core.tools import tool


@tool
def query_terminology(term: str, book_title: str = "") -> str:
    """查询术语翻译。优先查指定著作的 Memory Bank，再查全局 terminology 库。
    当遇到不确定的人名、地名、专有名词时使用。返回 "术语1: 译名1; 术语2: 译名2"
    形式的字符串；未命中返回空字符串。
    """
    if not term or not term.strip():
        return ""
    hits: List[tuple] = []
    terms = [t.strip() for t in term.split(",") if t.strip()]

    # 1) Per-book Memory Bank
    try:
        if book_title:
            from services.memory_bank_manager import memory_bank_manager
            bank = memory_bank_manager.get_bank(book_title)
            bank_terms = bank.get_terminology()
            for t in terms:
                for en, zh in bank_terms.items():
                    if t.lower() in en.lower() or en.lower() in t.lower():
                        hits.append((en, zh))
    except Exception:
        pass

    # 2) Global terminology service
    try:
        from services.terminology_service import terminology_service  # type: ignore
        for t in terms:
            try:
                res = terminology_service.search(t)  # type: ignore
                for item in (res or []):
                    if isinstance(item, dict):
                        en = item.get("en") or item.get("en_term") or t
                        zh = item.get("zh") or item.get("zh_term") or ""
                        if zh:
                            hits.append((en, zh))
            except Exception:
                continue
    except Exception:
        pass

    # 去重并格式化
    seen: dict = {}
    for en, zh in hits:
        if en and zh and en not in seen:
            seen[en] = zh
    if not seen:
        return ""
    return "; ".join(f"{en}: {zh}" for en, zh in list(seen.items())[:8])


@tool
def query_translation_memory(source_text: str, top_k: int = 3) -> str:
    """查询翻译记忆库，找历史上已翻译过的相似段落作为参考。
    当源文与已有翻译高度相似时可直接复用。返回 "原文 → 译文" 列表，未命中返回空串。
    """
    if not source_text or not source_text.strip():
        return ""
    try:
        from services.translation_memory import tm_instance
        from embedding_providers import EmbeddingManager
        emb = EmbeddingManager().embed([source_text], is_query=True)
        if not emb:
            return ""
        matches = tm_instance.search_by_embedding(emb[0], n_results=top_k, similarity_threshold=0.7)
        if not matches:
            return ""
        lines = []
        for m in matches[:top_k]:
            src = (m.get("source") or "")[:120].replace("\n", " ")
            tgt = (m.get("target") or "")[:120].replace("\n", " ")
            sim = m.get("similarity", 0)
            lines.append(f"[sim={sim:.2f}] {src} → {tgt}")
        return "\n".join(lines)
    except Exception:
        return ""


@tool
def query_knowledge_base(query: str, kb_ids_json: str = "[]", group: str = "", chapter: str = "") -> str:
    """跨知识库混合检索（向量 + 关键词）。kb_ids_json 是 KB ID 的 JSON 数组字符串，
    如 '["kb_xxx","kb_yyy"]'；留空则跨全部 KB。group/chapter 为作用域过滤。
    返回检索到的片段列表（每条 "KB名: 片段前 240 字"）。
    """
    try:
        kb_ids = json.loads(kb_ids_json) if kb_ids_json else []
    except Exception:
        kb_ids = []
    if not isinstance(kb_ids, list):
        kb_ids = []
    try:
        from services.hybrid_search import hybrid_query_multiple
        items = hybrid_query_multiple(
            kb_ids=kb_ids,
            query=query,
            group=group or None,
            chapter=chapter or None,
            top_k=3,
            score_threshold=0.35,
        )
        if not items:
            return ""
        lines = []
        for r in items[:3]:
            doc = (r.get("document") or "")[:240].replace("\n", " ")
            name = r.get("kb_name") or r.get("kb_id") or "kb"
            lines.append(f"[{name}] {doc}")
        return "\n".join(lines)
    except Exception:
        return ""


# 导出工具列表，供 chains.py 使用
ALL_TRANSLATION_TOOLS = [query_terminology, query_translation_memory, query_knowledge_base]
