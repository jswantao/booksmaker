# services/memory_bank.py — JSON 记忆库：术语公约 + 段落摘要 + 进度持久化
"""跨片段翻译上下文持久化：术语一致性、进度保存。
原子写入 + 自动备份 + 数据校验 + 过期清理。
"""

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from typing import List, Dict, Optional


class MemoryBank:
    """JSON 文件记忆库，维护翻译上下文一致性。

    优化特性:
    - 原子写入：先写 .tmp 再 os.replace，防止写入中断损坏数据
    - 自动备份：每次保存前将旧文件复制为 .bak
    - 数据校验：加载时校验结构完整性，自动修复缺失字段
    - 过期清理：摘要按时间戳自动淘汰，防止无限增长
    """

    # 保留策略
    MAX_RECENT_SUMMARIES = 5       # 最近摘要最大条数
    SUMMARY_TTL_DAYS = 30          # 摘要过期天数（超期自动清理）

    def __init__(self, file_path: str):
        self.file_path = file_path
        self._dirty = False        # 脏标记：是否有未保存的变更
        self._save_counter = 0     # 保存计数
        self._pending_updates = []  # 批量写入缓冲区
        self._batch_threshold = 10  # 缓冲区达到此数量时自动刷盘
        self.data = self._load()

    # ============================================================
    # 核心 I/O：原子写入 + 自动备份 + 数据校验
    # ============================================================

    def _load(self) -> Dict:
        """加载 JSON 文件，失败时从备份恢复，最后回退到默认结构"""
        raw = None

        # 1. 尝试加载主文件
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                print(f"[MemoryBank] Loaded: {self.file_path}")
            except (json.JSONDecodeError, OSError) as e:
                print(f"[MemoryBank] WARN 主文件损坏: {e}")

        # 2. 主文件失败 → 尝试从备份恢复
        if raw is None:
            bak_path = self.file_path + '.bak'
            if os.path.exists(bak_path):
                try:
                    with open(bak_path, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                    print(f"[MemoryBank] OK 从备份恢复: {bak_path}")
                except (json.JSONDecodeError, OSError) as e:
                    print(f"[MemoryBank] WARN 备份也损坏: {e}")

        # 3. 数据校验与修复
        if raw is not None:
            return self._validate_and_repair(raw)
        return self._default()

    def _validate_and_repair(self, raw: Dict) -> Dict:
        """校验 JSON 结构完整性，自动补全缺失字段"""
        default = self._default()
        repaired = False

        # 递归补全缺失的顶层键
        for key, default_value in default.items():
            if key not in raw:
                raw[key] = default_value
                repaired = True
                print(f"[MemoryBank] [修复] 缺失字段已补全: {key}")
            # 对于 dict 类型，递归补全子键
            elif isinstance(default_value, dict) and isinstance(raw[key], dict):
                for sub_key, sub_val in default_value.items():
                    if sub_key not in raw[key]:
                        raw[key][sub_key] = sub_val
                        repaired = True
                        print(f"[MemoryBank] [修复] 缺失子字段已补全: {key}.{sub_key}")

        if repaired:
            raw["updated_at"] = datetime.now().isoformat()
            print(f"[MemoryBank] OK 数据校验完成，已自动修复")

        return raw

    def _save(self):
        """原子保存：写临时文件 → os.replace 原子交换 → 备份旧文件

        os.replace() 在 POSIX 上是原子操作，Windows 上也是近乎原子的。
        即使进程崩溃，要么 .tmp 要么原文件完好，不会出现半写文件。
        """
        dir_path = os.path.dirname(self.file_path) or '.'
        os.makedirs(dir_path, exist_ok=True)

        self.data["updated_at"] = datetime.now().isoformat()
        self._save_counter += 1
        self._dirty = False

        # 1. 先写入临时文件
        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix='.json',
            prefix='.memory_tmp_',
            dir=dir_path
        )
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(tmp_fd)

            # 2. 备份旧文件
            if os.path.exists(self.file_path):
                bak_path = self.file_path + '.bak'
                try:
                    # copy2 可能因元数据复制失败，回退到 copyfile
                    try:
                        shutil.copy2(self.file_path, bak_path)
                    except OSError:
                        shutil.copyfile(self.file_path, bak_path)
                except OSError as e:
                    print(f"[MemoryBank] WARN 备份失败（继续保存）: {e}")

            # 3. 原子替换
            os.replace(tmp_path, self.file_path)

        except Exception:
            # 清理临时文件
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise

    def flush(self):
        """强制落盘（仅当有脏数据时）"""
        if self._dirty:
            self._save()

    def queue_update(self, update_type: str, data: dict):
        """
        入队更新操作，缓冲区满时自动刷盘。
        update_type: 'term' | 'summary' | 'chunk_done'
        data: 更新数据
        """
        self._pending_updates.append((update_type, data))
        if len(self._pending_updates) >= self._batch_threshold:
            self.flush_pending()

    def flush_pending(self):
        """批量处理缓冲区中的更新操作，一次性写入"""
        if not self._pending_updates:
            return

        for update_type, data in self._pending_updates:
            if update_type == 'term':
                en, zh = data.get('en', ''), data.get('zh', '')
                if en and en not in self.data["terminology"]:
                    self.data["terminology"][en] = zh
                    self._dirty = True
            elif update_type == 'summary':
                self._add_summary_internal(data.get('chunk', 0), data.get('summary', ''))
            elif update_type == 'chunk_done':
                self._mark_chunk_done_internal(data.get('chunk', 0))

        self._pending_updates.clear()
        if self._dirty:
            self._save()

    # ============================================================
    # 默认结构
    # ============================================================

    @staticmethod
    def _default() -> Dict:
        return {
            "project": "",
            "version": 2,  # 数据结构版本号（用于未来迁移）
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "terminology": {},           # {en_term: zh_term}  术语公约
            "recent_summaries": [],       # [{chunk, summary, time}] 最近段落摘要
            "completed_chapters": [],     # 已完成的章节标题
            "translated_chunks": [],      # 已完成的分段索引
            "progress": {"current_chunk": 0, "total_chunks": 0},
            "stats": {"total_tokens": 0, "chunks_done": 0, "total_saves": 0},
        }

    # ============================================================
    # 过期清理
    # ============================================================

    def _purge_expired(self):
        """清理过期的摘要"""
        now = datetime.now()
        purged = False

        # 清理过期摘要
        if self.data["recent_summaries"]:
            cutoff = now - timedelta(days=self.SUMMARY_TTL_DAYS)
            cutoff_str = cutoff.isoformat()
            keep = [
                s for s in self.data["recent_summaries"]
                if s.get("time", "") >= cutoff_str
            ]
            if len(keep) < len(self.data["recent_summaries"]):
                purged = True
            self.data["recent_summaries"] = keep[-self.MAX_RECENT_SUMMARIES:]

        if purged:
            self._dirty = True
            print(f"[MemoryBank] 已清理过期数据 "
                  f"(摘要保留 {len(self.data['recent_summaries'])})")

    # ============================================================
    # 术语管理
    # ============================================================

    def get_terminology(self) -> Dict[str, str]:
        return self.data.get("terminology", {})

    def add_term(self, en_term: str, zh_term: str):
        """添加术语（保守策略：已存在的旧译名不被覆盖）"""
        if en_term not in self.data["terminology"]:
            self.data["terminology"][en_term] = zh_term
            self._dirty = True
            self._save()

    def add_terms_batch(self, terms: Dict[str, str]):
        """批量添加术语"""
        added = 0
        for en, zh in terms.items():
            if en not in self.data["terminology"]:
                self.data["terminology"][en] = zh
                added += 1
        if added:
            self._dirty = True
            self._save()

    def remove_term(self, en_term: str) -> bool:
        """删除术语"""
        if en_term in self.data["terminology"]:
            del self.data["terminology"][en_term]
            self._dirty = True
            self._save()
            return True
        return False

    def search_terms(self, query: str) -> Dict[str, str]:
        """模糊搜索术语（支持英文/中文部分匹配）"""
        q = query.lower()
        results = {}
        for en, zh in self.data["terminology"].items():
            if q in en.lower() or q in zh:
                results[en] = zh
        return results

    # ============================================================
    # 摘要管理
    # ============================================================

    def _add_summary_internal(self, chunk_index: int, summary: str):
        """添加段落摘要（不触发保存）"""
        entry = {
            "chunk": chunk_index,
            "summary": summary[:300],
            "time": datetime.now().isoformat()
        }
        self.data["recent_summaries"].append(entry)

        # 按数量 + 时间双重淘汰
        if len(self.data["recent_summaries"]) > self.MAX_RECENT_SUMMARIES * 2:
            self._purge_expired()
        elif len(self.data["recent_summaries"]) > self.MAX_RECENT_SUMMARIES:
            self.data["recent_summaries"] = self.data["recent_summaries"][-self.MAX_RECENT_SUMMARIES:]

        self._dirty = True

    def add_summary(self, chunk_index: int, summary: str):
        """添加段落摘要（自动过期清理 + 立即保存）"""
        self._add_summary_internal(chunk_index, summary)
        self._save()

    # ============================================================
    # 进度管理
    # ============================================================

    def _mark_chunk_done_internal(self, chunk_index: int):
        """标记分段完成（不触发保存）"""
        if chunk_index not in self.data["translated_chunks"]:
            self.data["translated_chunks"].append(chunk_index)
        self.data["progress"]["current_chunk"] = chunk_index
        self.data["stats"]["chunks_done"] = len(self.data["translated_chunks"])
        self._dirty = True

    def mark_chunk_done(self, chunk_index: int):
        """标记分段完成（立即保存）"""
        self._mark_chunk_done_internal(chunk_index)
        self._save()

    def get_next_chunk(self) -> int:
        """获取下一个待翻译的分段索引，全部完成返回 -1"""
        done = set(self.data["translated_chunks"])
        total = self.data["progress"]["total_chunks"]
        for i in range(total):
            if i not in done:
                return i
        return -1

    def is_done(self) -> bool:
        """所有 chunk 翻译完成才返回 True，0 chunk 时返回 False"""
        total = self.data["progress"]["total_chunks"]
        if total <= 0:
            return False  # 翻译尚未启动
        return self.get_next_chunk() == -1

    def set_total_chunks(self, total: int):
        self.data["progress"]["total_chunks"] = total
        self._save()

    def get_progress_pct(self) -> float:
        """返回翻译进度百分比"""
        total = self.data["progress"]["total_chunks"]
        if total <= 0:
            return 0.0
        return len(self.data["translated_chunks"]) / total * 100

    # ============================================================
    # 上下文构建
    # ============================================================

    def build_context_prompt(self, max_chars: int = 800) -> str:
        """生成精简上下文 Prompt（术语公约 + 前文要点）"""
        # 先清理过期数据
        self._purge_expired()

        parts = []

        # 术语公约（取前 10 条）
        terms = self.get_terminology()
        if terms:
            term_lines = ["术语公约（必须严格遵循）："]
            for en, zh in list(terms.items())[:10]:
                term_lines.append(f"  {en} → {zh}")
            parts.append("\n".join(term_lines))

        # 前文摘要（最近 3 条）
        summaries = self.data["recent_summaries"]
        if summaries:
            smr_text = "前文要点：\n" + "\n".join(
                f"  [{s['chunk']}] {s['summary'][:150]}"
                for s in summaries[-3:]
            )
            parts.append(smr_text)

        ctx = "\n\n".join(parts)
        if len(ctx) > max_chars:
            ctx = ctx[:max_chars - 50] + "\n... [上下文已截断]"
        return ctx

    def extract_terms_from_translation(self, translation: str, source_text: str = ""):
        """从译文中提取术语并更新术语表（使用混合提取器）"""
        from services.term_extractor import term_extractor
        existing = self.get_terminology()
        terms = term_extractor.extract_with_rules(source_text, translation)
        added = 0
        for t in terms:
            en, zh = t.get("en", ""), t.get("zh", "")
            if en and zh and en not in existing:
                self.data["terminology"][en] = zh
                existing[en] = zh
                added += 1
                self._dirty = True
        if self._dirty:
            self._save()

    # ============================================================
    # 章节完成
    # ============================================================

    def mark_chapter_done(self, chapter_title: str):
        if chapter_title not in self.data["completed_chapters"]:
            self.data["completed_chapters"].append(chapter_title)
            self._dirty = True
            self._save()

    def get_chapter_stitch_context(self) -> str:
        """生成章节缝合所需的上下文（术语表 + 已完成章节列表）"""
        parts = []
        terms = self.get_terminology()
        if terms:
            term_lines = ["## 术语公约（全量）"]
            for en, zh in sorted(terms.items()):
                term_lines.append(f"  {en} → {zh}")
            parts.append("\n".join(term_lines))

        if self.data["completed_chapters"]:
            parts.append("## 已完成章节：" + "、".join(self.data["completed_chapters"]))

        return "\n\n".join(parts) if parts else ""

    # ============================================================
    # 诊断与统计
    # ============================================================

    def get_stats(self) -> Dict:
        """返回记忆库统计信息"""
        return {
            "file_path": self.file_path,
            "project": self.data.get("project", ""),
            "version": self.data.get("version", 1),
            "created_at": self.data.get("created_at", ""),
            "updated_at": self.data.get("updated_at", ""),
            "terms_count": len(self.data.get("terminology", {})),
            "summaries_count": len(self.data.get("recent_summaries", [])),
            "chapters_done": len(self.data.get("completed_chapters", [])),
            "chunks_done": len(self.data.get("translated_chunks", [])),
            "total_chunks": self.data["progress"]["total_chunks"],
            "progress_pct": round(self.get_progress_pct(), 1),
            "saves": self._save_counter,
            "dirty": self._dirty,
        }

    def integrity_check(self) -> Dict:
        """完整性检查：验证翻译进度与已翻译列表是否一致"""
        issues = []
        chunks_done = len(self.data.get("translated_chunks", []))
        stats_done = self.data["stats"]["chunks_done"]

        if chunks_done != stats_done:
            issues.append(
                f"translated_chunks 长度 ({chunks_done}) 与 stats.chunks_done "
                f"({stats_done}) 不一致，已自动修复"
            )
            self.data["stats"]["chunks_done"] = chunks_done

        current = self.data["progress"]["current_chunk"]
        total = self.data["progress"]["total_chunks"]
        if current > total and total > 0:
            issues.append(f"current_chunk ({current}) > total_chunks ({total})")

        if issues:
            self._dirty = True
            self._save()

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            **self.get_stats()
        }
