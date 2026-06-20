# services/memory_bank.py — JSON 记忆库：术语公约 + 段落摘要 + 进度持久化
"""跨片段翻译上下文持久化：术语一致性、论点追踪、进度保存"""

import json
import os
from datetime import datetime
from typing import List, Dict, Optional


class MemoryBank:
    """JSON 文件记忆库，维护翻译上下文一致性"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.data = self._load()

    def _load(self) -> Dict:
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self._default()

    def _save(self):
        os.makedirs(os.path.dirname(self.file_path) or '.', exist_ok=True)
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _default() -> Dict:
        return {
            "project": "",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "terminology": {},           # {en_term: zh_term}  术语公约
            "core_arguments": [],         # 核心论点摘要
            "recent_summaries": [],       # 最近5段的内容摘要
            "completed_chapters": [],     # 已完成的章节标题
            "translated_chunks": [],      # 已完成的分段索引
            "progress": {"current_chunk": 0, "total_chunks": 0},
            "stats": {"total_tokens": 0, "chunks_done": 0},
        }

    # ---- 术语管理 ----
    def get_terminology(self) -> Dict[str, str]:
        return self.data.get("terminology", {})

    def add_term(self, en_term: str, zh_term: str):
        """添加术语（保守策略：已存在的旧译名不被覆盖）"""
        if en_term not in self.data["terminology"]:
            self.data["terminology"][en_term] = zh_term
            self._save()

    def add_terms_batch(self, terms: Dict[str, str]):
        for en, zh in terms.items():
            if en not in self.data["terminology"]:
                self.data["terminology"][en] = zh
        self._save()

    # ---- 摘要管理 ----
    def add_summary(self, chunk_index: int, summary: str):
        """添加段落摘要（保留最近5条）"""
        self.data["recent_summaries"].append({
            "chunk": chunk_index,
            "summary": summary[:300],
            "time": datetime.now().isoformat()
        })
        if len(self.data["recent_summaries"]) > 5:
            self.data["recent_summaries"] = self.data["recent_summaries"][-5:]
        self._save()

    # ---- 进度管理 ----
    def mark_chunk_done(self, chunk_index: int):
        if chunk_index not in self.data["translated_chunks"]:
            self.data["translated_chunks"].append(chunk_index)
        self.data["progress"]["current_chunk"] = chunk_index
        self.data["stats"]["chunks_done"] = len(self.data["translated_chunks"])
        self.data["updated_at"] = datetime.now().isoformat()
        self._save()

    def get_next_chunk(self) -> int:
        """获取下一个待翻译的分段索引"""
        done = set(self.data["translated_chunks"])
        total = self.data["progress"]["total_chunks"]
        for i in range(total):
            if i not in done:
                return i
        return -1  # 全部完成

    def is_done(self) -> bool:
        return self.get_next_chunk() == -1

    def set_total_chunks(self, total: int):
        self.data["progress"]["total_chunks"] = total
        self._save()

    # ---- 上下文构建 ----
    def build_context_prompt(self, max_chars: int = 800) -> str:
        """生成精简上下文 Prompt（术语公约 + 前文要点 + 核心论点）"""
        parts = []

        # 术语公约（取前 10 条）
        terms = self.get_terminology()
        if terms:
            term_lines = ["术语公约（必须严格遵循）："]
            for en, zh in list(terms.items())[:10]:
                term_lines.append(f"  {en} → {zh}")
            parts.append("\n".join(term_lines))

        # 核心论点
        if self.data["core_arguments"]:
            args_text = "核心论点：\n" + "\n".join(
                f"  - {a}" for a in self.data["core_arguments"][:5])
            parts.append(args_text)

        # 前文摘要
        if self.data["recent_summaries"]:
            smr_text = "前文要点：\n" + "\n".join(
                f"  [{s['chunk']}] {s['summary'][:150]}" for s in self.data["recent_summaries"][-3:])
            parts.append(smr_text)

        ctx = "\n\n".join(parts)
        if len(ctx) > max_chars:
            ctx = ctx[:max_chars - 50] + "\n... [上下文已截断]"
        return ctx

    # ---- 核心论点管理 ----
    def add_core_argument(self, argument: str):
        """添加核心论点（去重）"""
        if argument not in self.data["core_arguments"]:
            self.data["core_arguments"].append(argument)
            # 保留最近 20 条
            if len(self.data["core_arguments"]) > 20:
                self.data["core_arguments"] = self.data["core_arguments"][-20:]
            self._save()

    def extract_terms_from_translation(self, translation: str, source_text: str = ""):
        """从译文中提取术语并更新术语表（保守策略：仅新增）"""
        import re
        # 提取中文专名模式：双书名号、间隔号人名
        found = {}
        # 书名号内容 → 可能是术语
        for match in re.finditer(r'《([^》]{2,30})》', translation):
            term = match.group(1)
            found[term] = term  # 中文术语直接存储

        # 间隔号人名
        for match in re.finditer(r'[一-鿿]{2,4}(?:·[一-鿿]{1,4}){1,2}', translation):
            term = match.group(0)
            found[term] = term

        if found:
            self.add_terms_batch(found)

    # ---- 章节完成 ----
    def mark_chapter_done(self, chapter_title: str):
        if chapter_title not in self.data["completed_chapters"]:
            self.data["completed_chapters"].append(chapter_title)
            self._save()

    def get_chapter_stitch_context(self) -> str:
        """生成章节缝合所需的上下文（术语表 + 已完成章节列表 + 核心论点）"""
        parts = []
        terms = self.get_terminology()
        if terms:
            term_lines = ["## 术语公约（全量）"]
            for en, zh in sorted(terms.items()):
                term_lines.append(f"  {en} → {zh}")
            parts.append("\n".join(term_lines))

        if self.data["completed_chapters"]:
            parts.append("## 已完成章节：" + "、".join(self.data["completed_chapters"]))

        if self.data["core_arguments"]:
            parts.append("## 核心论点：\n" + "\n".join(
                f"  {i+1}. {a}" for i, a in enumerate(self.data["core_arguments"])))

        return "\n\n".join(parts) if parts else ""
