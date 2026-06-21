# agents.py — Agent definitions v3
# Input/output concise, accurate, controllable
# Generation config (temperature, max_tokens, etc.) is managed by model_router.TASK_PROFILES
# as the single source of truth — Agent defines prompt identity and post-processing only.

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
import re

@dataclass
class Agent:
    name: str
    identity: str
    system_prompt: str
    version: str = "3.0.0"
    description: str = ""
    tags: List[str] = field(default_factory=list)
    preferred_task: str = "default"
    post_process: Optional[Callable[[str], str]] = None

    def build_system_prompt(self, **kwargs) -> str:
        prompt = self.system_prompt
        for k, v in kwargs.items():
            prompt = prompt.replace(f"{{{k}}}", str(v))
        return prompt.strip()

    def process_response(self, response: str) -> str:
        if self.post_process:
            return self.post_process(response)
        return response

def _clean_translation(text: str) -> str:
    # strip explanations, code fences, meta comments – controllable output
    text = re.sub(r'^(译文|翻译|输出|结果)[：:]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```[\w]*\n?', '', text)
    text = re.sub(r'\n*[\[\(]?注[：:].*$', '', text, flags=re.MULTILINE)
    # hard guard: strip any trailing glossary/term list
    text = re.split(r'\n- ["“][^"”]+["”]\s*[:：]', text)[0]
    return text.strip()

def _clean_epub(text: str) -> str:
    text = re.sub(r'```[\w]*\n?', '', text)
    text = text.strip()
    # ensure starts with <
    m = re.search(r'<[^>]+>', text)
    if m and m.start() > 0:
        text = text[m.start():]
    return text.strip()

# High-Frequency Task 1: Paragraph Translation
PARAGRAPH_TRANSLATOR = Agent(
    name="ParagraphTranslator",
    identity="段落翻译专家",
    tags=["翻译","段落","高频"],
    preferred_task="paragraph_translate",
    post_process=_clean_translation,
    system_prompt="""你是段落翻译官。中→英/英→中均可，默认英译中。

规则:
1. 准确完整，不增不漏
2. 术语一致: 严格遵循 {dynamic_terms}
3. 学术文体，流畅自然
4. 专名首次: 中文名(Original, 生卒年)
5. 数字日期保持原文格式

输出: 只输出译文纯文本，无解释、无术语表、无总结。
{dynamic_terms}"""
)

# High-Frequency Task 2: EPUB Replacement
EPUB_REPLACER = Agent(
    name="EpubReplacer",
    identity="EPUB 代码替换器",
    tags=["EPUB","替换","高频"],
    preferred_task="epub_replace",
    post_process=_clean_epub,
    system_prompt="""你是 EPUB 替换器。唯一任务: 将新译文精确替换进 XHTML，标签结构100%不变。

允许改: 文本节点内容
禁止改: 所有标签 <p><span><em>…、所有属性 class/id/style/epub:type/href…、空白缩进结构

中文用全角标点。
输出: 完整 XHTML 代码，无解释、无代码块标记。
"""
)

# Medium: KB Builder
KB_BUILDER = Agent(
    name="KBBuilder",
    identity="知识库构建器",
    tags=["知识库","构建"],
    preferred_task="kb_build",
    system_prompt="""你是知识库构建器。将外部文章结构化为检索片段。

输出 JSON 数组，每条: {"text":"…","group":"…","chapter":"…","keywords":["…"]}
要求: 
- 每条 200-500字，语义完整
- 标注 group/chapter，便于分组检索
- 提取3-5个关键词
只输出 JSON。
"""
)

# Low: Long-Text Translator
LONG_TRANSLATOR = Agent(
    name="LongTextTranslator",
    identity="长文翻译器",
    tags=["翻译","长文","低频"],
    preferred_task="long_text_translate",
    post_process=_clean_translation,
    system_prompt="""你是长文翻译官。保持全书术语一致、风格统一。

术语表: {dynamic_terms}
前文摘要: {context_summary}

输出: 纯译文，保持分段。
"""
)

# registry
AGENTS = {
    a.name: a for a in [
        PARAGRAPH_TRANSLATOR,
        EPUB_REPLACER,
        KB_BUILDER,
        LONG_TRANSLATOR,
    ]
}

# Reverse index: task_name -> Agent
AGENTS_BY_TASK: Dict[str, Agent] = {
    a.preferred_task: a for a in AGENTS.values() if a.preferred_task != "default"
}

def get_agent(name: str) -> Optional[Agent]:
    """Look up agent by name (e.g. 'ParagraphTranslator')."""
    return AGENTS.get(name)

def get_agent_by_task(task_name: str) -> Optional[Agent]:
    """Look up agent by task name (e.g. 'paragraph_translate')."""
    return AGENTS_BY_TASK.get(task_name)
