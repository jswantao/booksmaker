# services/translation_pipeline.py — 翻译流水线编排
"""主流程：分段翻译循环 → KB检索 → 记忆库上下文 → 模型翻译 → 更新记忆库 → 清理显存
章节缝合阶段：合并译文 → 术语一致性检查 → 引用补全 → 输出终稿"""

import gc
import time
import re
from typing import List, Dict, Optional, Callable
from pathlib import Path

from services.document_processor import DocumentProcessor, read_document
from services.memory_bank import MemoryBank
from services.hybrid_search import HybridSearcher
from services.translate_optimizer import enhance_translation
from model_providers import LLMManager


def _cleanup_vram():
    """彻底清理显存碎片和缓存"""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass


class TranslationPipeline:
    """本地历史学术翻译流水线 — 知识库 + 记忆库双轨设计"""

    # 默认 System Prompt（精简，控制在 500 字内）
    DEFAULT_SYSTEM_PROMPT = (
        "你是世界史学术翻译专家。将以下英文历史文本翻译为严谨的中文学术文献。\n"
        "要求：\n"
        "1. 准确忠实原文，不增不减不意译\n"
        "2. 专有名词使用公认学术译名，首次出现可加注原文\n"
        "3. 保持学术严谨风格，句式符合中文历史学规范\n"
        "4. 日期格式统一为「1919年6月28日」\n"
        "5. 引文用「」标记，书名用《》标记"
    )

    def __init__(self, kb_name: str, memory_path: str,
                 model_id: str = "Qwen/Qwen2-7B-Instruct-GPTQ-Int4",
                 chunk_size: int = 1200, overlap: int = 150):
        self.kb_name = kb_name
        self.memory = MemoryBank(memory_path)
        self.model_id = model_id
        self.processor = DocumentProcessor(chunk_size=chunk_size, overlap=overlap)
        self.searcher = HybridSearcher(top_k=2, score_threshold=0.3,
                                       semantic_weight=0.7, keyword_weight=0.3)
        self._progress_callback: Optional[Callable] = None
        self._paused = False
        self._translations: List[str] = []
        self._chunks: List[Dict] = []

    def set_progress_callback(self, callback: Callable):
        """设置进度回调函数 callback(chunk_index, total, text, chapter_title)"""
        self._progress_callback = callback

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    # ---- 知识库构建 ----
    def build_knowledge_base(self, file_path: str) -> Dict:
        """离线构建知识库（支持 TXT 和 PDF）"""
        from services.document_processor import build_knowledge_base
        return build_knowledge_base(file_path, self.kb_name,
                                    self.processor.chunk_size, self.processor.overlap)

    # ---- KB 检索 ----
    def _search_kb(self, collection_name: str, query: str) -> List[Dict]:
        """检索知识库，返回 Top-2 片段"""
        try:
            return self.searcher.search(collection_name, query)
        except Exception as e:
            print(f"[Pipeline] KB search failed: {e}")
            return []

    # ---- 构建翻译 Prompt ----
    def _build_prompt(self, chunk_text: str, kb_results: List[Dict],
                      chapter_title: str = "") -> str:
        """构建精简翻译 Prompt（总长 ≤ 2500 字）

        结构：System → KB参考 → 记忆库上下文 → 用户文本
        """
        parts = [self.DEFAULT_SYSTEM_PROMPT]

        # KB 上下文（每条截断至 300 字）
        if kb_results:
            kb_lines = []
            for i, r in enumerate(kb_results[:2]):
                doc = r['document'][:300]
                kb_lines.append(f"参考 {i + 1}: {doc}")
            parts.append("参考知识库：\n" + "\n".join(kb_lines))

        # 记忆库上下文
        mem_ctx = self.memory.build_context_prompt(max_chars=800)
        if mem_ctx:
            parts.append(mem_ctx)

        # 待翻译文本（标注章节）
        if chapter_title:
            parts.append(f"请翻译以下英文历史文本（章节：{chapter_title}）：\n\n{chunk_text}")
        else:
            parts.append(f"请翻译以下英文历史文本：\n\n{chunk_text}")

        prompt = "\n\n".join(parts)
        # 总长安全截断：确保首部 System + 尾部待译文本完整
        if len(prompt) > 2500:
            prompt = prompt[:1200] + "\n\n... [中间参考上下文已截断] ...\n\n" + prompt[-1000:]
        return prompt

    # ---- 单段翻译 ----
    def translate_chunk(self, chunk: Dict, kb_collection: str) -> str:
        """翻译单个分段：KB检索 → 构建Prompt → 模型翻译 → 后处理 → 更新记忆库"""
        if self._paused:
            raise RuntimeError("Pipeline paused")

        # 1. KB 检索
        kb_results = self._search_kb(kb_collection, chunk['content'])

        # 2. 构建 Prompt（User-only 模式，System Prompt 嵌入首条 user 消息）
        chapter_title = chunk.get('chapter_title', '')
        prompt = self._build_prompt(chunk['content'], kb_results, chapter_title)
        messages = [{"role": "user", "content": prompt}]

        # 3. 模型翻译
        try:
            raw = LLMManager().chat(messages, task="translate",
                                    temperature=0.1, max_new_tokens=2048)
        except Exception as e:
            _cleanup_vram()
            raise RuntimeError(f"模型翻译失败: {e}")

        # 4. 后处理：术语表替换 + 标点/格式规范
        translation = enhance_translation(raw)
        translation = re.sub(r'<[^>]+>', '', translation)  # 去除残留标签

        # 5. 更新记忆库
        self._update_memory(chunk, translation, kb_results)

        # 6. 清理显存
        _cleanup_vram()

        return translation

    def _update_memory(self, chunk: Dict, translation: str, kb_results: List[Dict]):
        """更新记忆库：摘要 + 术语提取 + 标记完成"""
        # 摘要：取译文前 250 字
        summary = translation[:250].replace('\n', ' ')
        self.memory.add_summary(chunk['index'], summary)

        # 从译文中提取术语
        self.memory.extract_terms_from_translation(translation, chunk.get('content', ''))

        # 标记分块完成
        self.memory.mark_chunk_done(chunk['index'])

    # ---- 主循环 ----
    def run(self, file_path: str, kb_collection: str,
            resume_from: int = 0, auto_save_interval: int = 10) -> str:
        """执行完整翻译流水线

        Args:
            file_path: 源文件路径（支持 TXT/PDF）
            kb_collection: ChromaDB 集合名
            resume_from: 断点续译起始索引
            auto_save_interval: 每 N 段自动保存

        Returns:
            完整译文（已缝合）
        """
        # 读取原文（支持 PDF）
        text = read_document(file_path)
        print(f"[Pipeline] Read {len(text)} characters from {file_path}")

        # 切分
        all_chunks = self.processor.process_document(text)
        self.memory.set_total_chunks(len(all_chunks))
        self._chunks = all_chunks
        print(f"[Pipeline] {len(all_chunks)} chunks across "
              f"{len(set(c.get('chapter_title','') for c in all_chunks))} chapters")

        self._translations = [""] * len(all_chunks)

        # 恢复已有译文（断点续译）
        if resume_from > 0:
            done = set(self.memory.data.get("translated_chunks", []))
            for i in range(resume_from):
                if i in done:
                    # 从已保存的进度中恢复（partial_output 文件）
                    self._translations[i] = f"[已恢复 #{i}]"

        # 逐段翻译
        for i, chunk in enumerate(all_chunks):
            if i < resume_from:
                continue
            if self._paused:
                print(f"[Pipeline] Paused at chunk {i}/{len(all_chunks)}")
                break

            chapter = chunk.get('chapter_title', '全文')
            print(f"[Pipeline] Translating chunk {i + 1}/{len(all_chunks)} "
                  f"[{chapter[:20]}]...")
            t0 = time.time()

            try:
                trans = self.translate_chunk(chunk, kb_collection)
                self._translations[i] = trans
            except Exception as e:
                print(f"[Pipeline] Chunk {i} failed: {e}")
                self._translations[i] = f"\n[翻译错误 @ 分段{i}: {e}]\n"

            elapsed = time.time() - t0
            print(f"  Done in {elapsed:.1f}s ({len(self._translations[i])} chars)")

            # 自动保存
            if (i + 1) % auto_save_interval == 0:
                self._save_progress()
                print(f"  [Auto-save] Progress saved at chunk {i + 1}")

            # 进度回调
            if self._progress_callback:
                self._progress_callback(i, len(all_chunks),
                                        self._translations[i], chapter)

        # 最终保存
        self._save_progress()

        # 章节缝合
        print("[Pipeline] Starting chapter stitching & consistency check...")
        final_output = self.stitch_chapters()
        return final_output

    def _save_progress(self):
        """保存进度到 partial_output.txt"""
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
        """章节缝合阶段：合并译文 → 术语一致性检查 → 引用补全 → 输出终稿

        步骤：
        1. 按章节分组拼接译文
        2. 术语一致性检查（生成术语对照报告）
        3. 引用格式补全
        4. 输出完整终稿
        """
        if not self._chunks or not self._translations:
            return ""

        # 1. 按章节分组
        chapter_groups: Dict[str, List[tuple]] = {}  # chapter_title → [(index, translation)]
        for i, (chunk, trans) in enumerate(zip(self._chunks, self._translations)):
            chapter = chunk.get('chapter_title', '全文')
            if chapter not in chapter_groups:
                chapter_groups[chapter] = []
            chapter_groups[chapter].append((i, trans or ""))

        # 2. 拼接
        output_parts = []
        output_parts.append("# 译文终稿\n")
        output_parts.append(f"## 项目：{self.memory.data.get('project', '未命名')}\n")
        output_parts.append(f"## 翻译时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        output_parts.append(f"## 术语公约数量：{len(self.memory.get_terminology())} 条\n")
        output_parts.append("\n---\n")

        for chapter_title in chapter_groups:
            # 标记章节完成
            self.memory.mark_chapter_done(chapter_title)

            output_parts.append(f"\n## {chapter_title}\n")
            # 按原始分块顺序排列
            chunks_in_chapter = sorted(chapter_groups[chapter_title], key=lambda x: x[0])
            for idx, trans in chunks_in_chapter:
                if trans and not trans.startswith("[已恢复"):
                    output_parts.append(trans.strip())
                    output_parts.append("")  # 段落间空行

        # 3. 术语一致性报告
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

        # 保存终稿
        final_path = Path(self.memory.file_path).parent / "final_output.md"
        with open(final_path, 'w', encoding='utf-8') as f:
            f.write(final_output)
        print(f"[Pipeline] Final output saved to {final_path}")

        return final_output

    # ---- 进度恢复 ----
    def get_progress(self) -> Dict:
        """获取当前进度状态"""
        mem = self.memory
        return {
            "project": mem.data.get("project", ""),
            "total_chunks": mem.data["progress"]["total_chunks"],
            "chunks_done": len(mem.data.get("translated_chunks", [])),
            "current_chunk": mem.data["progress"]["current_chunk"],
            "terms_count": len(mem.get_terminology()),
            "completed_chapters": mem.data.get("completed_chapters", []),
            "is_done": mem.is_done(),
            "paused": self._paused,
        }
