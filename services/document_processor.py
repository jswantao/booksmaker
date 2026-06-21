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

    # ---- 重叠分块（语义边界感知） ----
    def chunk_text(self, text: str) -> List[Dict]:
        """按字符数切分为重叠分块，在句子边界处断开。

        改进：
        - 在 chunk_size 的 60%-110% 范围内查找最近的句子边界
        - 重叠部分携带前一 chunk 的最后1-2句作为上下文
        """
        chunks = []
        start = 0
        idx = 0
        prev_tail = ""  # 前一 chunk 的尾部句子（上下文重叠）

        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk_content = text[start:end]

            # 在 60%-110% 范围内查找最近的句子/段落边界
            if end < len(text):
                best_boundary = -1
                search_start = int(self.chunk_size * 0.6)
                search_end = min(int(self.chunk_size * 1.1), len(chunk_content))

                # 查找范围内的所有边界位置
                for sep in ['。\n', '。\n\n', '.\n', '。\n', '\n\n', '。', '. ']:
                    pos = chunk_content.rfind(sep, search_start, search_end)
                    if pos > best_boundary:
                        best_boundary = pos + len(sep) - 1

                if best_boundary > search_start:
                    end = start + best_boundary + 1
                    chunk_content = text[start:end]

            # 添加前一 chunk 的尾部作为上下文前缀
            content = chunk_content.strip()
            if prev_tail and idx > 0:
                content = f"[前文] {prev_tail}\n\n{content}"

            chunks.append({
                "index": idx,
                "content": content,
                "char_start": start,
                "char_end": end,
            })

            # 保存当前 chunk 的最后1-2句作为下一 chunk 的上下文
            sentences = re.split(r'[。.!?\n]+', chunk_content)
            sentences = [s.strip() for s in sentences if s.strip()]
            prev_tail = "。".join(sentences[-2:]) if len(sentences) >= 2 else (sentences[-1] if sentences else "")
            if len(prev_tail) > 200:
                prev_tail = prev_tail[-200:]

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
    """读取 TXT/PDF/EPUB 文件，返回文本内容"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    suffix = path.suffix.lower()
    if suffix == '.pdf':
        return _read_pdf(file_path)
    elif suffix == '.epub':
        return _read_epub(file_path)
    elif suffix in ('.txt', '.md', '.text'):
        return _read_text(file_path)
    else:
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


def _read_epub(file_path: str) -> str:
    """读取 EPUB 文件，提取所有章节纯文本"""
    try:
        from ebooklib import epub
    except ImportError:
        raise ImportError("读取 EPUB 需要 ebooklib 库。请运行: pip install ebooklib")

    from bs4 import BeautifulSoup

    book = epub.read_epub(file_path)
    chapters = []

    for item in book.get_items():
        if item.get_type() == 9:  # ITEM_DOCUMENT = 9 (XHTML)
            try:
                content = item.get_content().decode('utf-8')
                soup = BeautifulSoup(content, 'html.parser')
                text = soup.get_text(separator='\n', strip=True)
                if text.strip():
                    chapters.append(text)
            except Exception as e:
                print(f"[EPUB] Skip item {item.get_name()}: {e}")

    if not chapters:
        for item in book.get_items():
            try:
                content = item.get_content().decode('utf-8')
                soup = BeautifulSoup(content, 'html.parser')
                text = soup.get_text(separator='\n', strip=True)
                if len(text) > 100:
                    chapters.append(text)
            except Exception:
                pass

    return "\n\n".join(chapters)
