# services/translation_pipeline.py — v3 optimized
# High: Paragraph Translation + EPUB Replacement
# Medium: KB Construction
# Low: Long-Text Translation
# Automatic Memory Base Auto-Construction

import time, re
from typing import List, Dict, Optional
from pathlib import Path

from services.model_router import model_router
from services.memory_bank_manager import memory_bank_manager
from agents_lcel.chains import build_translate_runnable
from agents_lcel.postprocess import get_cleaner

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

    def translate_chunk(self, text: str, group: str = None, chapter: str = None) -> str:
        if self._paused: raise RuntimeError("paused")
        route = model_router.resolve_provider(self.task)
        try:
            chain = build_translate_runnable(
                task=self.task,
                source_text=text,
                book_title=self.book_title,
                kb_ids=self.kb_ids or None,
                group=group or "",
                chapter=chapter or "",
                use_tm=True,
                use_rag=bool(self.kb_ids),
                model_name=route.get("model", ""),
            )
            raw = chain.invoke({"input": text})
        except Exception:
            # Fallback: retry with default task if specific task fails
            chain = build_translate_runnable(
                task="paragraph_translate",
                source_text=text,
                book_title=self.book_title,
                kb_ids=self.kb_ids or None,
                group=group or "",
                chapter=chapter or "",
                model_name=route.get("model", ""),
            )
            raw = chain.invoke({"input": text})
        out = get_cleaner(self.task)(raw)
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
        out_dir = Path(memory_bank_manager._get_bank_path(self.book_title)).parent if self.book_title else Path(memory_bank_manager.BASE_DIR) / "_general"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "final_output.md").write_text(final, encoding="utf-8")
        return final
