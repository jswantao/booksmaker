# services/translation_pipeline.py — v3 optimized
# High: Paragraph Translation + EPUB Replacement
# Medium: KB Construction
# Low: Long-Text Translation
# Automatic Memory Base Auto-Construction

import time, re
from typing import List, Dict, Optional
from pathlib import Path

from services.model_router import model_router
from services.hybrid_search import hybrid_query_multiple
from services.memory_bank_manager import memory_bank_manager
from model_providers import LLMManager
from agents import get_agent

class TranslationPipeline:
    """Concise, controllable pipeline"""

    def __init__(self, book_title: str,
                 kb_ids: List[str] = None,
                 task: str = "long_text_translate"):
        self.book_title = book_title.strip()
        self.kb_ids = kb_ids or []
        self.task = task if task in ("paragraph_translate","long_text_translate") else "long_text_translate"
        # dedicated memory base per book
        self.memory = memory_bank_manager.get_bank(self.book_title if self.book_title else None)
        self._paused = False

    def pause(self): self._paused = True
    def resume(self): self._paused = False

    def _search_kb(self, query: str, group: str = None, chapter: str = None):
        if not self.kb_ids: return []
        return hybrid_query_multiple(self.kb_ids, query, group=group, chapter=chapter, top_k=2, score_threshold=0.35)

    def translate_chunk(self, text: str, group: str = None, chapter: str = None) -> str:
        if self._paused: raise RuntimeError("paused")
        # KB retrieval: must use only relevant group/chapter content
        kb_hits = self._search_kb(text[:300], group=group, chapter=chapter)
        agent_name = "ParagraphTranslator" if self.task=="paragraph_translate" else "LongTextTranslator"
        agent = get_agent(agent_name)
        terms = self.memory.get_terminology()
        terms_text = " | ".join(f"{en}→{zh}" for en,zh in list(terms.items())[:12]) if terms else "(无)"
        ctx_sum = self.memory.build_context_prompt(400)
        sys = agent.build_system_prompt(dynamic_terms=terms_text, context_summary=ctx_sum)
        messages = [{"role":"system","content":sys}]
        if kb_hits:
            snip = "\n".join(h["document"][:220] for h in kb_hits[:2])
            messages.append({"role":"system","content":f"参考:{snip}"})
        messages.append({"role":"user","content":text})
        route = model_router.resolve_provider(self.task)
        gen = model_router.get_generation_kwargs(self.task)
        llm = LLMManager()
        try:
            raw = llm.chat(messages, task="translate", **gen)
        except Exception:
            raw = llm.chat(messages, task="default", **gen)
        out = agent.process_response(raw)
        # Automatic Memory Base Auto-Construction
        if self.book_title:
            self.memory.auto_build_from_translation(text, out)
        return out

    def run_long_text(self, file_path: str, chunk_size: int = 1200, overlap: int = 120) -> str:
        # Low frequency: Long-Text Translation
        text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        # simple chunk
        chunks = []
        i=0
        while i < len(text):
            chunks.append(text[i:i+chunk_size])
            i += chunk_size - overlap
        results = []
        for idx, ch in enumerate(chunks):
            if self._paused: break
            try:
                tr = self.translate_chunk(ch)
            except Exception as e:
                tr = f"[错误 {idx}: {e}]"
            results.append(tr)
            if idx % 5 == 0:
                # concise auto-save
                pass
        final = "\n\n".join(results)
        # save final
        out_dir = Path(memory_bank_manager._get_bank_path(self.book_title)).parent if self.book_title else Path("memory_banks/_general")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "final_output.md").write_text(final, encoding="utf-8")
        return final
