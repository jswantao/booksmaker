# services/term_extractor.py — 混合术语提取器
# 两阶段提取：高置信度规则提取 + LLM辅助提取（仅在规则不足时）

import re
import json
from typing import List, Dict


class TermExtractor:
    """混合术语提取：规则 + LLM"""

    # 高置信度正则模式
    HIGH_CONFIDENCE_PATTERNS = [
        # 书名号内容（中文书名）
        (r'《([^》]{2,30})》', '书名'),
        # 引号+括号注释（通常是人名原文）
        (r'"([^"]{2,20})"(?:（[^）]+）)', '人名'),
        # 中文后的英文括号（原文标注）
        (r'（([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)）', '原文标注'),
        # 中文间隔号人名（如 查士丁尼·大帝）
        (r'([一-鿿]{2,4}(?:·[一-鿿]{1,4}){1,3})', '人名'),
    ]

    def extract_with_rules(self, source: str, translation: str) -> List[Dict]:
        """规则提取，置信度高"""
        terms = []
        seen = set()

        for pattern, category in self.HIGH_CONFIDENCE_PATTERNS:
            for match in re.finditer(pattern, translation):
                term = match.group(1).strip()
                if len(term) < 2 or term in seen:
                    continue
                seen.add(term)
                terms.append({
                    "zh": term,
                    "en": self._find_english_counterpart(term, source),
                    "category": category,
                    "confidence": "high"
                })

        return terms

    def _find_english_counterpart(self, zh_term: str, source: str) -> str:
        """尝试从原文中找到对应的英文术语"""
        # 简单启发式：在原文中查找大写开头的词组
        # 这个方法不完美，但作为辅助信息足够
        if not source:
            return ""

        # 查找原文中可能在括号内出现的术语
        for match in re.finditer(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3})\b', source):
            candidate = match.group(1)
            if len(candidate) > 3:
                return candidate
        return ""

    def extract_with_llm(self, source: str, translation: str,
                         existing_terms: Dict[str, str],
                         llm_chat_fn=None) -> List[Dict]:
        """
        LLM提取新术语，仅当规则提取不足3条时调用。
        llm_chat_fn: 接受messages列表返回文本的函数
        """
        if not llm_chat_fn:
            return []

        # 构建已收录术语摘要
        existing_summary = json.dumps(
            dict(list(existing_terms.items())[:20]),
            ensure_ascii=False
        )[:200]

        prompt = f"""从以下翻译对中提取专业术语（人名、地名、制度名、专有概念）。
已收录术语：{existing_summary}
只输出JSON数组，格式：[{{"en": "English term", "zh": "中文译名", "category": "人名|地名|制度|概念"}}]
不要输出其他内容。如果没有新术语，输出空数组 []。

原文：{source[:500]}
译文：{translation[:500]}"""

        try:
            result = llm_chat_fn([{"role": "user", "content": prompt}])
            # 解析JSON结果
            result = result.strip()
            if result.startswith("```"):
                result = result.split("\n", 1)[-1].rsplit("```", 1)[0]
            terms = json.loads(result)
            if isinstance(terms, list):
                return [
                    {**t, "confidence": "medium"}
                    for t in terms[:10]
                    if isinstance(t, dict) and "zh" in t
                ]
        except (json.JSONDecodeError, Exception) as e:
            print(f"[TermExtractor] LLM extraction failed: {e}")

        return []

    def extract(self, source: str, translation: str,
                existing_terms: Dict[str, str],
                llm_chat_fn=None, min_rules: int = 3) -> List[Dict]:
        """
        混合提取：先规则，不足时补LLM。
        返回所有提取到的术语列表。
        """
        # 第一阶段：规则提取
        rule_terms = self.extract_with_rules(source, translation)

        # 第二阶段：规则不足3条时，调用LLM补充
        if len(rule_terms) < min_rules and llm_chat_fn:
            llm_terms = self.extract_with_llm(
                source, translation, existing_terms, llm_chat_fn
            )
            # 去重合并
            seen_zh = {t["zh"] for t in rule_terms}
            for t in llm_terms:
                if t["zh"] not in seen_zh:
                    rule_terms.append(t)
                    seen_zh.add(t["zh"])

        return rule_terms


# 全局单例
term_extractor = TermExtractor()
