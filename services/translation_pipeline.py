# services/translation_pipeline.py — 翻译流水线编排 (v2: 知识库与源文本分离)
"""主流程：源文本切分 → 多KB检索 → 记忆库上下文 → 模型翻译 → 更新记忆库 → 清理显存
章节缝合阶段：合并译文 → 术语一致性检查 → 引用补全 → 输出终稿

v2 改进：
- 知识库与待翻译文本完全分离，KB 可跨书复用
- 支持多知识库同时检索
- KB 为可选配置（无 KB 时直接翻译）
- 支持 TXT / PDF / EPUB 源文件
"""

import time
import re
from typing import List, Dict, Optional, Callable
from pathlib import Path

from utils.cuda import cleanup_if_local
from services.context_budget import ContextBudget
from services.document_processor import DocumentProcessor, read_document
from services.memory_bank_manager import memory_bank_manager
from services.hybrid_search import HybridSearcher, hybrid_query_multiple
from model_providers import LLMManager


class TranslationContext:
    """长文翻译的滑动窗口上下文。

    维护最近 N 个 chunk 的译文尾部和累积术语，
    为下一个 chunk 提供连贯的前文参考。
    """

    def __init__(self, window_size: int = 3):
        self.window_size = window_size
        self._recent: List[Dict] = []  # 最近 N 个 chunk 的上下文
        self._accumulated_terms: Dict[str, str] = {}

    def add_translation(self, source: str, target: str, terms: Dict[str, str] = None):
        """记录一个 chunk 的翻译结果"""
        self._recent.append({
            "source_tail": source[-200:] if source else "",
            "target_tail": target[-200:] if target else "",
        })
        # 保持窗口大小
        if len(self._recent) > self.window_size:
            self._recent = self._recent[-self.window_size:]
        # 累积术语
        if terms:
            self._accumulated_terms.update(terms)

    def build_context(self) -> str:
        """为下一个 chunk 构建滑动窗口上下文"""
        if not self._recent and not self._accumulated_terms:
            return ""

        parts = []

        # 前文译文尾部（帮助连贯性）
        for i, ctx in enumerate(self._recent):
            tail = ctx.get("target_tail", "").strip()
            if tail:
                parts.append(f"前文参考({i + 1}): {tail}")

        # 累积术语（确保一致性）
        if self._accumulated_terms:
            import json
            terms_text = json.dumps(
                dict(list(self._accumulated_terms.items())[:15]),
                ensure_ascii=False
            )[:300]
            parts.append(f"已确认术语: {terms_text}")

        return "\n".join(parts)


class TranslationPipeline:
    """本地历史学术翻译流水线 — 知识库 + 记忆库双轨设计

    v2 架构：
    - 待翻译源文件 (TXT/PDF/EPUB) — 仅做切分，不入库
    - 外部知识库列表 (0-N 个 ChromaDB 集合) — 提供背景/术语/史料参考
    - 记忆库 (JSON) — 术语公约 + 段落摘要 + 进度
    """

    DEFAULT_SYSTEM_PROMPT = (
        
    )

    def __init__(self, memory_path: str,
                 kb_collections: List[str] = None,
                 kb_ids: List[str] = None,
                 model_id: str = "Qwen/Qwen2-7B-Instruct",
                 chunk_size: int = 1200, overlap: int = 150):
        """
        Args:
            memory_path: 记忆库 JSON 文件路径
            kb_collections: ChromaDB 集合名列表（外部知识库，可选）
            kb_ids: 知识库 ID 列表（用于跨 KB 混合检索，可选）
            model_id: 本地翻译模型 ID
            chunk_size: 分块大小（字符数）
            overlap: 分块重叠（字符数）
        """
        self.memory = memory_bank_manager.load_from_path(memory_path)
        self.kb_collections = kb_collections or []
        self.kb_ids = kb_ids or []
        self.model_id = model_id
        self.processor = DocumentProcessor(chunk_size=chunk_size, overlap=overlap)
        self.searcher = HybridSearcher(top_k=2, score_threshold=0.3,
                                       semantic_weight=0.7, keyword_weight=0.3)
        self._context = TranslationContext(window_size=3)
        self._progress_callback: Optional[Callable] = None
        self._paused = False
        self._translations: List[str] = []
        self._chunks: List[Dict] = []
        self._last_error: str = ""

    def set_progress_callback(self, callback: Callable):
        self._progress_callback = callback

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    # ---- KB 检索（多知识库混合） ----
    def _search_all_kbs(self, query: str) -> List[Dict]:
        """检索所有已配置的知识库，返回去重合并后的 Top-2 结果"""
        if not self.kb_collections and not self.kb_ids:
            return []

        results = []

        # 方式1: 通过 kb_ids 跨多 KB 混合检索
        if self.kb_ids:
            try:
                items = hybrid_query_multiple(self.kb_ids, query, top_k=2,
                                              score_threshold=0.3,
                                              semantic_weight=0.7, keyword_weight=0.3)
                results.extend(items)
            except Exception as e:
                print(f"[Pipeline] Multi-KB hybrid search failed: {e}")

        # 方式2: 通过 collection_name 逐个检索（兼容旧接口）
        for col_name in self.kb_collections:
            try:
                kb_results = self.searcher.search(col_name, query)
                for r in kb_results:
                    r['kb_name'] = col_name
                results.extend(kb_results)
            except Exception as e:
                print(f"[Pipeline] KB '{col_name}' search failed: {e}")

        # 去重 + 按分数排序
        seen = set()
        unique = []
        for r in sorted(results, key=lambda x: x.get('score', 0), reverse=True):
            h = r.get('document', '')[:100]
            if h not in seen:
                seen.add(h)
                unique.append(r)
        return unique[:2]

    # ---- 构建翻译 Prompt ----
    def _build_prompt(self, chunk_text: str, kb_results: List[Dict],
                      chapter_title: str = "") -> str:
        """构建翻译 Prompt（使用 ContextBudget 协调各部分预算）"""
        budget = ContextBudget(max_chars=8000, reserved_for_output=2000)

        # 计算预算
        chapter_hint = f"（章节：{chapter_title}）" if chapter_title else ""
        user_instruction = (
            f"请将以下英文历史文本翻译为中文{chapter_hint}。"
            f"只输出译文，不要添加总结或评论。\n\n{chunk_text}"
        )
        alloc = budget.allocate(self.DEFAULT_SYSTEM_PROMPT, user_instruction)

        parts = [self.DEFAULT_SYSTEM_PROMPT]

        # KB 上下文（按 rag_budget 截断，每条≤300字，标注来源）
        if kb_results:
            rag_limit = alloc["rag_budget"]
            kb_lines = []
            used = 0
            for i, r in enumerate(kb_results[:3]):
                doc = r.get('document', '')[:300]
                src = r.get('kb_name', '') or r.get('kb_id', '')
                label = f"参考 {i + 1}" + (f" [{src}]" if src else "")
                line = f"{label}: {doc}"
                if used + len(line) > rag_limit:
                    break
                kb_lines.append(line)
                used += len(line)
            if kb_lines:
                parts.append("参考知识库：\n" + "\n".join(kb_lines))

        # 记忆库上下文（按 memory_budget 截断）
        mem_limit = alloc["memory_budget"]
        mem_ctx = self.memory.build_context_prompt(max_chars=mem_limit)
        if mem_ctx:
            parts.append(mem_ctx)

        # 滑动窗口上下文（前文译文尾部 + 累积术语）
        window_ctx = self._context.build_context()
        if window_ctx:
            parts.append(f"前文连贯性参考：\n{window_ctx}")

        # 待翻译文本
        parts.append(user_instruction)

        prompt = "\n\n".join(parts)
        # 最终安全网
        return budget.build_safety_net(prompt)

    # ---- 单段翻译 ----
    def translate_chunk(self, chunk: Dict) -> str:
        """翻译单个分段：KB检索 → 构建Prompt → 模型翻译 → 后处理 → 更新记忆库"""
        if self._paused:
            raise RuntimeError("Pipeline paused")

        # 1. 检索所有知识库
        kb_results = self._search_all_kbs(chunk['content'])

        # 2. 构建 Prompt
        chapter_title = chunk.get('chapter_title', '')
        prompt = self._build_prompt(chunk['content'], kb_results, chapter_title)
        messages = [{"role": "user", "content": prompt}]

        # 3. 模型翻译
        try:
            raw = LLMManager().chat(messages, task="translate",
                                    temperature=0.1, max_new_tokens=2048)
        except Exception as e:
            cleanup_if_local()
            raise RuntimeError(f"模型翻译失败: {e}")

        # 4. 后处理（使用记忆库动态术语）
        glossary = self.memory.get_terminology()
        translation = enhance_translation(raw, glossary=glossary)
        translation = re.sub(r'<[^>]+>', '', translation)

        # 5. 更新记忆库
        self._update_memory(chunk, translation)

        # 6. 清理显存
        cleanup_if_local()

        return translation

    def _update_memory(self, chunk: Dict, translation: str):
        """更新记忆库：摘要 + 术语提取 + 标记完成 + 滑动窗口"""
        summary = translation[:250].replace('\n', ' ')
        self.memory.add_summary(chunk['index'], summary)
        self.memory.extract_terms_from_translation(translation, chunk.get('content', ''))
        self.memory.mark_chunk_done(chunk['index'])

        # 更新滑动窗口上下文
        terms = self.memory.get_terminology()
        self._context.add_translation(
            source=chunk.get('content', ''),
            target=translation,
            terms=terms
        )

    # ---- 主循环 ----
    def run(self, file_path: str,
            resume_from: int = 0, auto_save_interval: int = 10) -> str:
        """执行完整翻译流水线

        Args:
            file_path: 源文件路径（支持 TXT/PDF/EPUB）
            resume_from: 断点续译起始索引
            auto_save_interval: 每 N 段自动保存

        Returns:
            完整译文（已缝合）
        """
        # 读取原文
        try:
            text = read_document(file_path)
            ext = Path(file_path).suffix.lower()
            print(f"[Pipeline] Read {len(text)} chars from {file_path} ({ext})")
            if not text.strip():
                self._last_error = f"文件读取为空: {file_path}"
                print(f"[Pipeline] ERROR: {self._last_error}")
                return f"[错误] {self._last_error}"
        except Exception as e:
            self._last_error = f"文件读取失败: {e}"
            print(f"[Pipeline] ERROR: {self._last_error}")
            return f"[错误] {self._last_error}"

        # 切分
        all_chunks = self.processor.process_document(text)
        self.memory.set_total_chunks(len(all_chunks))
        self._chunks = all_chunks
        chapter_count = len(set(c.get('chapter_title', '') for c in all_chunks))
        kb_count = len(self.kb_collections) + len(self.kb_ids)
        print(f"[Pipeline] {len(all_chunks)} chunks / {chapter_count} chapters "
              f"(KBs: {kb_count}, resume: {resume_from})")

        self._translations = [""] * len(all_chunks)

        # 逐段翻译
        for i, chunk in enumerate(all_chunks):
            if i < resume_from:
                continue
            if self._paused:
                print(f"[Pipeline] Paused at chunk {i}/{len(all_chunks)}")
                break

            chapter = chunk.get('chapter_title', '全文')
            print(f"[Pipeline] Chunk {i + 1}/{len(all_chunks)} [{chapter[:30]}]...")
            t0 = time.time()

            try:
                trans = self.translate_chunk(chunk)
                self._translations[i] = trans
            except Exception as e:
                print(f"[Pipeline] Chunk {i} failed: {e}")
                self._translations[i] = f"\n[翻译错误 @ 分段{i}: {e}]\n"

            elapsed = time.time() - t0
            print(f"  Done in {elapsed:.1f}s ({len(self._translations[i])} chars)")

            if (i + 1) % auto_save_interval == 0:
                self._save_progress()
                print(f"  [Auto-save] chunk {i + 1}")

            if self._progress_callback:
                self._progress_callback(i, len(all_chunks),
                                        self._translations[i], chapter)

        self._save_progress()

        print("[Pipeline] Chapter stitching...")
        final_output = self.stitch_chapters()
        return final_output

    def _save_progress(self):
        output_path = Path(self.memory.file_path).parent / "partial_output.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            for i, (chunk, trans) in enumerate(zip(self._chunks, self._translations)):
                chapter = chunk.get('chapter_title', '')
                f.write(f"--- Chunk {i} [{chapter}] ---\n")
                f.write((trans or f"[未翻译]") + "\n\n")
        self.memory._save()
        print(f"[Pipeline] Progress saved to {output_path}")

    # ---- 章节缝合 ----
    def stitch_chapters(self) -> str:
        """章节缝合：合并译文 → 术语一致性报告 → 输出终稿"""
        if not self._chunks or not self._translations:
            return ""

        chapter_groups: Dict[str, List[tuple]] = {}
        for i, (chunk, trans) in enumerate(zip(self._chunks, self._translations)):
            chapter = chunk.get('chapter_title', '全文')
            if chapter not in chapter_groups:
                chapter_groups[chapter] = []
            chapter_groups[chapter].append((i, trans or ""))

        output_parts = []
        output_parts.append("# 译文终稿\n")
        output_parts.append(f"## 项目：{self.memory.data.get('project', '未命名')}\n")
        output_parts.append(f"## 翻译时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        output_parts.append(f"## 术语公约数量：{len(self.memory.get_terminology())} 条\n")
        output_parts.append(f"## 参考知识库：{len(self.kb_collections) + len(self.kb_ids)} 个\n")
        output_parts.append("\n---\n")

        for chapter_title in chapter_groups:
            self.memory.mark_chapter_done(chapter_title)
            output_parts.append(f"\n## {chapter_title}\n")
            chunks_in_chapter = sorted(chapter_groups[chapter_title], key=lambda x: x[0])
            for idx, trans in chunks_in_chapter:
                if trans and not trans.startswith("[已恢复"):
                    output_parts.append(trans.strip())
                    output_parts.append("")

        # 术语报告
        output_parts.append("\n---\n")
        output_parts.append("\n## 附录：术语公约对照表\n")
        terms = self.memory.get_terminology()
        if terms:
            output_parts.append("| 英文 | 中文译名 |")
            output_parts.append("|------|----------|")
            for en, zh in sorted(terms.items()):
                output_parts.append(f"| {en} | {zh} |")
        else:
            output_parts.append("（无已确认术语公约）")

        final_output = "\n".join(output_parts)

        final_path = Path(self.memory.file_path).parent / "final_output.md"
        with open(final_path, 'w', encoding='utf-8') as f:
            f.write(final_output)
        print(f"[Pipeline] Final output saved to {final_path}")

        return final_output

    def get_progress(self) -> Dict:
        mem = self.memory
        progress = mem.data.get("progress", {})
        return {
            "project": mem.data.get("project", ""),
            "total_chunks": progress.get("total_chunks", 0),
            "chunks_done": len(mem.data.get("translated_chunks", [])),
            "current_chunk": progress.get("current_chunk", 0),
            "terms_count": len(mem.get_terminology()),
            "completed_chapters": mem.data.get("completed_chapters", []),
            "is_done": mem.is_done(),
            "paused": self._paused,
            "kb_count": len(self.kb_collections) + len(self.kb_ids),
            "last_error": self._last_error,
        }
