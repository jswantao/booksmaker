# agents_lcel/postprocess.py — Output post-processing (extracted from agents.py)
#
# Clean functions for LLM output: strip prefixes, code fences, annotations,
# and ensure EPUB output starts with valid XHTML tags.
#
# These replace the Agent.post_process callbacks from the legacy agents.py.

from __future__ import annotations

import re
from typing import Callable, Dict, Optional


def clean_translation(text: str) -> str:
    """Strip translation prefixes, code fences, annotations, and trailing glossary."""
    text = re.sub(r'^(译文|翻译|输出|结果)[：:]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```[\w]*\n?', '', text)
    text = re.sub(r'\n*[\[\(]?注[：:].*$', '', text, flags=re.MULTILINE)
    # hard guard: strip any trailing glossary/term list
    text = re.split(r'\n- [""\u201c\u201d][^""\u201c\u201d]+[""\u201c\u201d]\s*[:：]', text)[0]
    return text.strip()


def clean_epub(text: str) -> str:
    """Strip code fences and ensure output starts with an XHTML tag."""
    text = re.sub(r'```[\w]*\n?', '', text)
    text = text.strip()
    # ensure starts with <
    m = re.search(r'<[^>]+>', text)
    if m and m.start() > 0:
        text = text[m.start():]
    return text.strip()


# Task → cleaner mapping
_CLEANERS: Dict[str, Optional[Callable[[str], str]]] = {
    "paragraph_translate": clean_translation,
    "long_text_translate": clean_translation,
    "epub_replace": clean_epub,
    "kb_build": None,
    "term_extract": None,
    "default": None,
}


def get_cleaner(task: str) -> Callable[[str], str]:
    """Return the post-processing function for a given task.

    Returns identity function (no-op) if no cleaner is registered.
    """
    cleaner = _CLEANERS.get(task)
    if cleaner is None:
        return lambda x: x
    return cleaner
