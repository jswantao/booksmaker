# services/document_processor.py — 文档预处理：章节切分 + 术语提取 + 重叠分块
"""离线文档处理管线：按章节切分 → 术语提取 → 重叠分块。支持 TXT 和 PDF 文件。"""

import re
from pathlib import Path
from typing import List, Dict, Tuple, Union


class DocumentProcessor:
    """历史学术文献预处理"""

    def __init__(self, chunk_size: int = 1200, overlap: int = 150):
        self.chunk_size = chunk_size
        self.overlap = overlap

    # ---- 章节切分 ----
    @staticmethod
    def split_chapters(text: str) -> List[Dict[str, str]]:
        """按章节标题切分文本。识别模式：第X章 / 第X节 / Chapter X / === 分隔符"""
        # 通用章节分割模式
        chapter_patterns = [
            r'(?:^|\n)(第[一二三四五六七八九十百千\d]+[章节部篇卷])',
            r'(?:^|\n)(Chapter\s+\d+)',
            r'(?:^|\n)(\d+[\.\、]\s*\S)',
            r'(?:^|\n)(={3,}\s*\n)',
        ]

        # 尝试模式匹配
        for pattern in chapter_patterns:
            parts = re.split(pattern, text, flags=re.MULTILINE)
            if len(parts) > 3:  # 至少切出 2 段以上才算有效
                chapters = []
                for i in range(0, len(parts) - 1, 2):
                    title = (parts[i] if parts[i].strip() else "前言")
                    content = parts[i + 1] if i + 1 < len(parts) else ""
                    chapters.append({"title": title.strip(), "content": content.strip()})
                return chapters

        # 回退：整篇作为一个章节
        return [{"title": "全文", "content": text}]

    # ---- 重叠分块 ----
    def chunk_text(self, text: str) -> List[Dict]:
        """按字符数切分为重叠分块。每块约 chunk_size 字符，前后 overlap 字符重叠"""
        chunks = []
        start = 0
        idx = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk_content = text[start:end]

            # 尽量在句号/段落边界处截断
            if end < len(text):
                # 向后找最近的句子边界
                boundary = max(
                    chunk_content.rfind('。'),
                    chunk_content.rfind('. '),
                    chunk_content.rfind('\n'),
                )
                if boundary > self.chunk_size * 0.6:
                    end = start + boundary + 1
                    chunk_content = text[start:end]

            chunks.append({
                "index": idx,
                "content": chunk_content.strip(),
                "char_start": start,
                "char_end": end,
            })
            start = end - self.overlap
            idx += 1
        return chunks

    def process_document(self, text: str) -> List[Dict]:
        """完整处理流程：章节切分 → 分块"""
        chapters = self.split_chapters(text)
        all_chunks = []
        for ch in chapters:
            chunks = self.chunk_text(ch["content"])
            for ck in chunks:
                ck["chapter_title"] = ch["title"]
            all_chunks.extend(chunks)
        return all_chunks

    # ---- 术语提取（简易版） ----
    @staticmethod
    def extract_terms(text: str, min_freq: int = 3) -> List[Tuple[str, int]]:
        """提取疑似专有名词（大写开头连续词、中文专名模式）"""
        terms = {}

        # 英文大写开头词组
        for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b', text):
            term = match.group(1)
            terms[term] = terms.get(term, 0) + 1

        # 中文专名模式：人名·人名、地名等
        for match in re.finditer(r'[一-鿿]{2,4}(?:·[一-鿿]{1,4}){1,2}', text):
            term = match.group(0)
            terms[term] = terms.get(term, 0) + 1

        # 书名号内容
        for match in re.finditer(r'《([^》]{2,30})》', text):
            term = match.group(1)
            terms[term] = terms.get(term, 0) + 1

        return sorted(
            [(t, c) for t, c in terms.items() if c >= min_freq],
            key=lambda x: x[1], reverse=True
        )


# ---- 文件读取 ----
def read_document(file_path: str) -> str:
    """读取 TXT 或 PDF 文件，返回文本内容"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    suffix = path.suffix.lower()
    if suffix == '.pdf':
        return _read_pdf(file_path)
    elif suffix in ('.txt', '.md', '.text'):
        return _read_text(file_path)
    else:
        # 默认按文本文件读取
        return _read_text(file_path)


def _read_text(file_path: str) -> str:
    """读取纯文本文件"""
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def _read_pdf(file_path: str) -> str:
    """读取 PDF 文件，提取纯文本"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError("读取 PDF 需要 PyMuPDF 库。请运行: pip install PyMuPDF")

    doc = fitz.open(file_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        if text.strip():
            pages.append(text)
    doc.close()
    return "\n\n".join(pages)


# ---- 知识库构建入口 ----
def build_knowledge_base(file_path: str, kb_name: str, chunk_size: int = 1200,
                         overlap: int = 150):
    """离线构建知识库：读取文件 → 切分 → 嵌入 → 存入 ChromaDB。支持 TXT 和 PDF。"""
    from services.knowledge_manager import kb_manager
    from services.knowledge_service import add_to_knowledge

    print(f"[KB Builder] Processing: {file_path}")
    text = read_document(file_path)
    print(f"[KB Builder] Read {len(text)} characters")

    processor = DocumentProcessor(chunk_size=chunk_size, overlap=overlap)
    chapters = processor.split_chapters(text)
    print(f"[KB Builder] Found {len(chapters)} chapters")

    # 创建或获取 KB
    existing = kb_manager.get_all_kbs()
    target = next((k for k in existing if k['name'] == kb_name), None)
    if not target:
        target = kb_manager.create_kb(name=kb_name, description=f"Auto-built from {Path(file_path).name}",
                                      embedding_model="bge")
        print(f"[KB Builder] Created KB: {target['name']}")

    # 按章节逐段添加
    total_chunks = 0
    for ch in chapters:
        chunks = processor.chunk_text(ch['content'])
        if not chunks:
            continue
        texts = [f"[{ch['title']}] {c['content']}" for c in chunks]
        add_to_knowledge(target['collection_name'], texts, [
            {"source": str(Path(file_path).name), "chapter": ch['title'], "chunk": str(c['index'])}
            for c in chunks
        ])
        total_chunks += len(chunks)
        print(f"  Chapter '{ch['title'][:30]}': {len(chunks)} chunks added")

    kb_manager.update_document_count(target['id'])
    print(f"[KB Builder] Done: {total_chunks} chunks in KB '{kb_name}'")
    return target
