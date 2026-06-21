# services/epub_replacer.py — 基于 DOM 解析的 EPUB 文本替换
# 将文本替换从 LLM 任务降级为确定性 DOM 操作
# LLM 只负责翻译纯文本，替换由 BeautifulSoup 精确完成

import difflib
from typing import Dict, List, Tuple
from bs4 import BeautifulSoup, NavigableString


class EPUBTextReplacer:
    """基于 DOM 解析的精确文本替换，不依赖 LLM。

    策略：
    1. 解析 XHTML 为 DOM 树（BeautifulSoup html.parser）
    2. 遍历文本节点，精确或模糊匹配原文
    3. 替换文本内容，保留所有标签、属性、CSS 类
    4. 重新序列化为 XHTML 字符串
    """

    def replace_text(self, epub_code: str, translations: Dict[str, str]) -> Tuple[str, int]:
        """精确文本替换

        Args:
            epub_code: 原始 XHTML/EPUB 代码
            translations: {原文片段: 译文片段} 映射

        Returns:
            (替换后的代码, 成功替换次数)
        """
        soup = BeautifulSoup(epub_code, 'html.parser')
        replaced_count = 0

        for text_node in soup.find_all(string=True):
            if not isinstance(text_node, NavigableString):
                continue
            node_text = str(text_node)
            for original, translated in translations.items():
                if original and original in node_text:
                    new_text = node_text.replace(original, translated)
                    text_node.replace_with(NavigableString(new_text))
                    replaced_count += 1
                    break  # 一个节点只替换一次

        return str(soup), replaced_count

    def replace_paragraphs(self, epub_code: str,
                           paragraph_map: Dict[str, str]) -> Tuple[str, int]:
        """段落级替换：匹配整个 <p> 或 <div> 内的文本内容

        Args:
            epub_code: 原始 XHTML 代码
            paragraph_map: {原文段落完整文本: 译文段落} 映射

        Returns:
            (替换后的代码, 成功替换次数)
        """
        soup = BeautifulSoup(epub_code, 'html.parser')
        replaced_count = 0

        for tag in soup.find_all(['p', 'div', 'span', 'h1', 'h2', 'h3', 'h4']):
            tag_text = tag.get_text(strip=True)
            for original, translated in paragraph_map.items():
                original_stripped = original.strip()
                if original_stripped and original_stripped == tag_text:
                    # 保留标签结构，只替换内部文本
                    tag.string = translated
                    replaced_count += 1
                    break

        return str(soup), replaced_count

    def replace_with_fuzzy_match(self, epub_code: str,
                                  translations: Dict[str, str],
                                  threshold: float = 0.85) -> Tuple[str, int]:
        """模糊匹配替换：处理 LLM 翻译后的文本可能与原文不完全对应的情况

        使用 difflib.SequenceMatcher 计算相似度，超过阈值则替换。

        Args:
            epub_code: 原始 XHTML 代码
            translations: {原文: 译文} 映射
            threshold: 最低相似度（0-1）

        Returns:
            (替换后的代码, 成功替换次数)
        """
        soup = BeautifulSoup(epub_code, 'html.parser')
        replaced_count = 0

        # 收集所有文本节点
        text_nodes = []
        for node in soup.find_all(string=True):
            if isinstance(node, NavigableString) and node.strip():
                text_nodes.append(node)

        for node in text_nodes:
            node_text = str(node)
            best_match = None
            best_ratio = 0.0

            for original, translated in translations.items():
                if not original:
                    continue
                # 快速预筛：长度差异过大则跳过
                if abs(len(node_text) - len(original)) > len(original) * 0.5:
                    continue
                ratio = difflib.SequenceMatcher(None, node_text, original).ratio()
                if ratio > best_ratio and ratio >= threshold:
                    best_ratio = ratio
                    best_match = translated

            if best_match is not None:
                node.replace_with(NavigableString(best_match))
                replaced_count += 1

        return str(soup), replaced_count

    def replace_full_text(self, epub_code: str, new_translation: str) -> Tuple[str, int]:
        """全文替换：用新译文替换 HTML 中所有文本节点内容，保留标签结构。

        用于「用户提供新译文 + EPUB 代码」场景：
        1. 解析 HTML，收集所有文本节点
        2. 找到最主要的文本节点（字符数最多的）
        3. 用新译文替换该节点的内容

        Args:
            epub_code: 原始 EPUB HTML 代码
            new_translation: 新译文（纯文本）

        Returns:
            (替换后代码, 替换节点数)
        """
        soup = BeautifulSoup(epub_code, 'html.parser')
        text_nodes = []

        for node in soup.find_all(string=True):
            if isinstance(node, NavigableString) and node.strip():
                text_nodes.append(node)

        if not text_nodes:
            return epub_code, 0

        # 找到最长的文本节点（通常是正文主体）
        main_node = max(text_nodes, key=lambda n: len(str(n).strip()))
        original = str(main_node)

        # 如果新旧文本相似度很高（>90%），说明是同一段的不同翻译版本，直接替换
        ratio = difflib.SequenceMatcher(None, original.strip(), new_translation.strip()).ratio()

        if ratio > 0.3:
            # 用新译文替换
            main_node.replace_with(NavigableString(new_translation))
            return str(soup), 1

        # 相似度太低，尝试在父级标签层面替换
        parent = main_node.parent
        if parent and parent.name in ('p', 'div', 'span', 'blockquote', 'section'):
            parent.string = new_translation
            return str(soup), 1

        return epub_code, 0

    def batch_replace(self, epub_code: str,
                      translations: Dict[str, str]) -> Tuple[str, Dict]:
        """批量替换：先精确匹配，再模糊匹配剩余项

        Args:
            epub_code: 原始 XHTML 代码
            translations: {原文: 译文} 映射

        Returns:
            (替换后代码, {"exact": int, "fuzzy": int, "unmatched": list})
        """
        # 第一轮：精确替换
        code, exact_count = self.replace_text(epub_code, translations)

        # 找出未被精确替换的项
        soup_check = BeautifulSoup(code, 'html.parser')
        all_text = " ".join(
            str(n) for n in soup_check.find_all(string=True)
            if isinstance(n, NavigableString)
        )
        remaining = {
            orig: trans for orig, trans in translations.items()
            if orig and orig not in all_text and orig not in code
        }

        # 第二轮：对未匹配项做模糊匹配
        fuzzy_count = 0
        unmatched = []
        if remaining:
            code, fuzzy_count = self.replace_with_fuzzy_match(
                code, remaining, threshold=0.80
            )
            # 检查仍未匹配的
            soup_final = BeautifulSoup(code, 'html.parser')
            final_text = str(soup_final)
            for orig in remaining:
                if orig not in final_text:
                    unmatched.append(orig)

        return code, {
            "exact": exact_count,
            "fuzzy": fuzzy_count,
            "unmatched": unmatched[:5],  # 只返回前5个未匹配项
        }


# 全局单例
epub_replacer = EPUBTextReplacer()
