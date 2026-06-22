# agents_lcel/prompts.py — LCEL ChatPromptTemplate 版本
#
# 把 agents.py 中 4 段 system prompt 原样迁移为 ChatPromptTemplate，
# 保留所有 {dynamic_terms} / {context_summary} / {epub_constraints} 占位符。
# 注意：原始 prompt 中出现的 JSON 示例 {} 必须用 {{ }} 转义，否则
# ChatPromptTemplate.from_messages 会把它当成变量占位符。

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


# ---------------------------------------------------------------------------
# 段落翻译 (paragraph_translate)
# ---------------------------------------------------------------------------
PARAGRAPH_TRANSLATE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是段落翻译官。中→英/英→中均可，默认英译中。

规则:
1. 准确完整，不增不漏
2. 术语一致: 严格遵循 {dynamic_terms}
3. 学术文体，流畅自然
4. 专名首次: 中文名(Original, 生卒年)
5. 数字日期保持原文格式

输出: 只输出译文纯文本，无解释、无术语表、无总结。
术语参考: {dynamic_terms}

{epub_constraints}""",
    ),
    MessagesPlaceholder(variable_name="context_messages", optional=True),
    ("human", "{input}"),
])


# ---------------------------------------------------------------------------
# EPUB 替换 (epub_replace)
# ---------------------------------------------------------------------------
EPUB_REPLACE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是 EPUB 替换器。唯一任务: 将新译文精确替换进 XHTML，标签结构100%不变。

允许改: 文本节点内容
禁止改: 所有标签 <p><span><em>…、所有属性 class/id/style/epub:type/href…、空白缩进结构

中文用全角标点。
输出: 完整 XHTML 代码，无解释、无代码块标记。

{epub_constraints}""",
    ),
    ("human", "{input}"),
])


# ---------------------------------------------------------------------------
# 知识库构建 (kb_build)
# ---------------------------------------------------------------------------
KB_BUILD_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是知识库构建器。将外部文章结构化为检索片段。

输出 JSON 数组，每条: {{"text":"…","group":"…","chapter":"…","keywords":["…"]}}
要求:
- 每条 200-500字，语义完整
- 标注 group/chapter，便于分组检索
- 提取3-5个关键词
只输出 JSON。""",
    ),
    ("human", "{input}"),
])


# ---------------------------------------------------------------------------
# 长文翻译 (long_text_translate)
# ---------------------------------------------------------------------------
LONG_TEXT_TRANSLATE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """你是长文翻译官。保持全书术语一致、风格统一。

术语表: {dynamic_terms}
前文摘要: {context_summary}

输出: 纯译文，保持分段。""",
    ),
    MessagesPlaceholder(variable_name="context_messages", optional=True),
    ("human", "{input}"),
])


# ---------------------------------------------------------------------------
# 索引：task name → prompt template
# ---------------------------------------------------------------------------
PROMPTS_BY_TASK = {
    "paragraph_translate": PARAGRAPH_TRANSLATE_PROMPT,
    "epub_replace": EPUB_REPLACE_PROMPT,
    "kb_build": KB_BUILD_PROMPT,
    "long_text_translate": LONG_TEXT_TRANSLATE_PROMPT,
    # 默认 fallback 也用段落翻译 prompt
    "translate": PARAGRAPH_TRANSLATE_PROMPT,
    "default": PARAGRAPH_TRANSLATE_PROMPT,
    "epub": EPUB_REPLACE_PROMPT,
}


def get_prompt_for_task(task: str) -> ChatPromptTemplate:
    """按 task name 取 prompt template，找不到就 fallback 到段落翻译。"""
    return PROMPTS_BY_TASK.get(task, PARAGRAPH_TRANSLATE_PROMPT)
