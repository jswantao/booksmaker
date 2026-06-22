# agents_lcel/__init__.py — LCEL Agent 包
#
# 把 agents.py 中的 prompt / post_process 用 LangChain LCEL 重写。
# 主要导出:
#   - get_prompt_for_task(task) -> ChatPromptTemplate
#   - build_chain_for_task(task, use_tools, model_name, prompt_kwargs) -> Runnable
#   - build_translate_runnable(...) -> Runnable (翻译专用)
#   - prequery_context_for_injection(...) -> str (工具结果拼成 prompt 片段)
#   - query_terminology / query_translation_memory / query_knowledge_base (@tool)
#   - clean_translation / clean_epub / get_cleaner (后处理函数)

from agents_lcel.prompts import (
    EPUB_REPLACE_PROMPT,
    KB_BUILD_PROMPT,
    LONG_TEXT_TRANSLATE_PROMPT,
    PARAGRAPH_TRANSLATE_PROMPT,
    PROMPTS_BY_TASK,
    get_prompt_for_task,
)
from agents_lcel.tools import (
    ALL_TRANSLATION_TOOLS,
    query_knowledge_base,
    query_terminology,
    query_translation_memory,
)
from agents_lcel.chains import (
    build_chain_for_task,
    build_translate_runnable,
    prequery_context_for_injection,
)
from agents_lcel.postprocess import (
    clean_translation,
    clean_epub,
    get_cleaner,
)

__all__ = [
    "PARAGRAPH_TRANSLATE_PROMPT",
    "EPUB_REPLACE_PROMPT",
    "KB_BUILD_PROMPT",
    "LONG_TEXT_TRANSLATE_PROMPT",
    "PROMPTS_BY_TASK",
    "get_prompt_for_task",
    "query_terminology",
    "query_translation_memory",
    "query_knowledge_base",
    "ALL_TRANSLATION_TOOLS",
    "build_chain_for_task",
    "build_translate_runnable",
    "prequery_context_for_injection",
    "clean_translation",
    "clean_epub",
    "get_cleaner",
]
