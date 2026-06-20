# services/epub_service.py — EPUB 文件生成
# 模块职责：将 AI 生成的 EPUB 代码文本构建为合法 .epub 文件

import re
import uuid
from pathlib import Path
from typing import Optional
from config import Config, EBOOKLIB_AVAILABLE

config = Config()

if EBOOKLIB_AVAILABLE:
    from ebooklib import epub


def build_epub_file(epub_code: str, title: str = "Translated_Book") -> Optional[Path]:
    if not EBOOKLIB_AVAILABLE:
        return None

    epub_dir = Path(config.UPLOAD_DIR) / "epub"
    epub_dir.mkdir(exist_ok=True)

    safe_title = re.sub(r'[\\/*?:"<>|]', '', title).strip() or "book"
    safe_title = safe_title[:50]
    output_path = epub_dir / f"{safe_title}_{uuid.uuid4().hex[:8]}.epub"

    try:
        book = epub.EpubBook()
        book.set_identifier(str(uuid.uuid4()))
        book.set_title(title)
        book.set_language('zh')
        book.add_author('AI Translation Workbench')

        code_blocks = re.findall(r'```(?:xml|html|xhtml|css)?\s*\n(.*?)```', epub_code,
                                 re.DOTALL | re.IGNORECASE)

        if not code_blocks:
            sections = re.split(r'(?:^|\n)(?:文件|File)\s*[:：]\s*', epub_code, flags=re.IGNORECASE)
            if len(sections) < 2:
                code_blocks = [epub_code]
            else:
                code_blocks = [s.strip() for s in sections[1:]]

        css_content = ""
        xhtml_chapters = []

        for block in code_blocks:
            block = block.strip()
            if not block: continue
            if block.startswith('<?xml') or '<html' in block.lower():
                xhtml_chapters.append(block)
            elif '{' in block and any(k in block for k in ('color', 'font', 'margin', 'padding')):
                css_content = block
            elif '<p' in block or '<div' in block or '<h' in block.lower():
                xhtml_chapters.append(block)
            else:
                xhtml_chapters.append(
                    f'<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html><html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh"><head><title>{title}</title></head><body>{block}</body></html>')

        if not xhtml_chapters:
            xhtml_chapters.append(epub_code)

        if css_content:
            css_item = epub.EpubItem(uid="style", file_name="style/default.css", media_type="text/css",
                                     content=css_content.encode('utf-8'))
            book.add_item(css_item)

        spine = ['nav']
        toc_list = []
        for i, xhtml in enumerate(xhtml_chapters):
            ch_id = f'chapter_{i + 1}'
            file_name = f'chapter_{i + 1}.xhtml'
            chapter = epub.EpubHtml(title=f'Chapter {i + 1}', file_name=file_name, lang='zh')
            clean_xhtml = re.sub(r'<\?xml.*?\?>', '', xhtml)
            clean_xhtml = re.sub(r'<!DOCTYPE[^>]*>', '', clean_xhtml, flags=re.IGNORECASE)
            chapter.content = clean_xhtml.encode('utf-8')
            book.add_item(chapter)
            spine.append(chapter)
            toc_list.append(epub.Link(file_name, f'Chapter {i + 1}', ch_id))

        book.toc = toc_list
        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        epub.write_epub(str(output_path), book)
        return output_path
    except Exception as e:
        print(f"EPUB build failed: {e}")
        return None
