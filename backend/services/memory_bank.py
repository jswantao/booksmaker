# services/memory_bank.py — JSON 记忆库 v3 (concise, per-book)
"""跨片段翻译上下文持久化：术语一致性、进度保存。
原子写入 + 自动备份 + 数据校验 + 过期清理。
v3: 强制简洁、按书隔离、无书名不写入。
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class MemoryBank:
    """Concise per-book memory bank"""

    # Concise by design
    MAX_RECENT_SUMMARIES = 3       # was 5 -> 3
    SUMMARY_TTL_DAYS = 14          # was 30 -> 14
    MAX_TERMS_IN_PROMPT = 12       # cap terms injected
    MAX_SUMMARY_CHARS = 180        # concise summaries
    MAX_TERMS_STORED = 300         # hard cap to keep bank lean

    def __init__(self, file_path: str, book_title: Optional[str] = None, read_only: bool = False):
        self.file_path = file_path
        self.book_title = book_title or ""
        self.read_only = read_only  # general translation: read-only, no writes
        self._dirty = False
        self._save_counter = 0
        self.data = self._load()

    # ---------- I/O ----------
    def _load(self) -> Dict:
        raw = None
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
            except Exception as e:
                print(f"[MemoryBank] WARN load failed: {e}")
        if raw is None:
            bak = self.file_path + '.bak'
            if os.path.exists(bak):
                try:
                    with open(bak, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                    print(f"[MemoryBank] recovered from {bak}")
                except Exception:
                    pass
        if raw is not None:
            return self._validate_and_repair(raw)
        return self._default()

    def _default(self) -> Dict:
        return {
            "book_title": self.book_title,
            "version": 3,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "terminology": {},
            "recent_summaries": [],
            "completed_chapters": [],
            "translated_chunks": [],
            "progress": {"current_chunk": 0, "total_chunks": 0},
            "stats": {"chunks_done": 0, "saves": 0},
        }

    def _validate_and_repair(self, raw: Dict) -> Dict:
        default = self._default()
        for k, v in default.items():
            if k not in raw:
                raw[k] = v
            elif isinstance(v, dict) and isinstance(raw[k], dict):
                for sk, sv in v.items():
                    raw[k].setdefault(sk, sv)
        # enforce caps immediately
        terms = raw.get("terminology", {})
        if len(terms) > self.MAX_TERMS_STORED:
            # keep most recent / sorted stable: truncate
            raw["terminology"] = dict(list(terms.items())[:self.MAX_TERMS_STORED])
        raw.setdefault("book_title", self.book_title)
        return raw

    def _save(self):
        if self.read_only:
            return  # DO NOT store translations when no book_title / read_only
        dir_path = os.path.dirname(self.file_path) or '.'
        os.makedirs(dir_path, exist_ok=True)
        self.data["updated_at"] = datetime.now().isoformat()
        self.data["book_title"] = self.book_title
        self._save_counter += 1
        self._dirty = False

        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.json', prefix='.mb_', dir=dir_path)
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            if os.path.exists(self.file_path):
                try:
                    shutil.copyfile(self.file_path, self.file_path + '.bak')
                except Exception:
                    pass
            os.replace(tmp_path, self.file_path)
        except Exception:
            if os.path.exists(tmp_path):
                try: os.unlink(tmp_path)
                except: pass
            raise

    def flush(self):
        if self._dirty and not self.read_only:
            self._save()

    # ---------- terms ----------
    def get_terminology(self) -> Dict[str, str]:
        return self.data.get("terminology", {})

    def add_term(self, en_term: str, zh_term: str) -> bool:
        if self.read_only: return False
        terms = self.data["terminology"]
        if en_term in terms: return False  # conservative: don't overwrite
        if len(terms) >= self.MAX_TERMS_STORED:
            # evict oldest (first inserted)
            first = next(iter(terms))
            del terms[first]
        terms[en_term] = zh_term
        self._dirty = True
        self._save()
        return True

    def add_terms_batch(self, terms: Dict[str, str]) -> int:
        if self.read_only: return 0
        added = 0
        store = self.data["terminology"]
        for en, zh in terms.items():
            if en not in store and len(store) < self.MAX_TERMS_STORED:
                store[en] = zh
                added += 1
        if added:
            self._dirty = True
            self._save()
        return added

    def remove_term(self, en_term: str) -> bool:
        """Remove a term from the terminology dictionary."""
        if self.read_only:
            return False
        store = self.data.get("terminology", {})
        if en_term not in store:
            return False
        del store[en_term]
        self._dirty = True
        self._save()
        return True

    # ---------- summaries concise ----------
    def add_summary(self, chunk_index: int, summary: str):
        if self.read_only: return
        # purge expired first
        self._purge_expired()
        entry = {
            "chunk": chunk_index,
            "summary": summary[:self.MAX_SUMMARY_CHARS],
            "time": datetime.now().isoformat()
        }
        s = self.data["recent_summaries"]
        s.append(entry)
        # keep only last N
        if len(s) > self.MAX_RECENT_SUMMARIES:
            self.data["recent_summaries"] = s[-self.MAX_RECENT_SUMMARIES:]
        self._dirty = True
        self._save()

    def _purge_expired(self):
        s = self.data.get("recent_summaries", [])
        if not s: return
        cutoff = (datetime.now() - timedelta(days=self.SUMMARY_TTL_DAYS)).isoformat()
        new_s = [x for x in s if x.get("time", "") >= cutoff]
        if len(new_s) != len(s):
            self.data["recent_summaries"] = new_s[-self.MAX_RECENT_SUMMARIES:]
            self._dirty = True

    # ---------- progress ----------
    def mark_chunk_done(self, chunk_index: int):
        if self.read_only: return
        done = self.data["translated_chunks"]
        if chunk_index not in done:
            done.append(chunk_index)
        self.data["progress"]["current_chunk"] = chunk_index
        self.data["stats"]["chunks_done"] = len(done)
        self._dirty = True
        self._save()

    def set_total_chunks(self, total: int):
        if self.read_only: return
        self.data["progress"]["total_chunks"] = total
        self._dirty = True
        self._save()

    # ---------- context build: concise & controllable ----------
    def build_context_prompt(self, max_chars: int = 600) -> str:
        """Concise controllable context: terms + 2 summaries max"""
        self._purge_expired()
        parts = []
        terms = self.get_terminology()
        if terms:
            # take most relevant first 12
            lines = [f"{en}→{zh}" for en, zh in list(terms.items())[:self.MAX_TERMS_IN_PROMPT]]
            parts.append("术语:" + " | ".join(lines))
        summaries = self.data.get("recent_summaries", [])[-2:]
        if summaries:
            sm = " ".join(s["summary"][:120] for s in summaries)
            parts.append(f"前文:{sm}")
        ctx = "\n".join(parts)
        if len(ctx) > max_chars:
            ctx = ctx[:max_chars-20] + "...[截断]"
        return ctx

    # ---------- auto memory construction from translation ----------
    @staticmethod
    def _extract_terms_from_translation(source: str, translation: str):
        """Regex-based term extraction from source+translation pair.
        Returns list of {zh, en} dicts. Inlined from former term_extractor.py."""
        import re
        terms = []
        seen = set()
        patterns = [
            (r'《([^》]{2,30})》', '书名'),
            (r'"([^"]{2,20})"(?:（[^）]+）)', '人名'),
            (r'（([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)）', '原文标注'),
            (r'([一-鿿]{2,4}(?:·[一-鿿]{1,4}){1,3})', '人名'),
        ]
        for pattern, _category in patterns:
            for match in re.finditer(pattern, translation):
                term = match.group(1).strip()
                if len(term) < 2 or term in seen: continue
                seen.add(term)
                en = ""
                if source:
                    en_match = re.search(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3})\b', source)
                    if en_match and len(en_match.group(1)) > 3:
                        en = en_match.group(1)
                terms.append({"zh": term, "en": en})
        return terms

    def auto_build_from_translation(self, source: str, translation: str):
        """Automatic Mechanism: build reasonable memory base from translation result"""
        if self.read_only or not self.book_title:
            return 0
        existing = self.get_terminology()
        terms = self._extract_terms_from_translation(source, translation)
        added = 0
        for t in terms[:5]:  # cap per chunk to keep memory concise
            en, zh = t.get("en",""), t.get("zh","")
            if en and zh and en not in existing and len(en) < 60 and len(zh) < 30:
                if self.add_term(en, zh):
                    added += 1
                    existing[en] = zh
        # concise summary
        summ = translation.replace("\n"," ")[:self.MAX_SUMMARY_CHARS]
        # chunk index auto-increment
        next_idx = len(self.data["translated_chunks"])
        self.add_summary(next_idx, summ)
        self.mark_chunk_done(next_idx)
        return added
