# services/translate_optimizer.py — 翻译增强：术语表 + 后处理 + 上下文截断
"""提供术语表替换、后处理规则、上下文Token优化"""

import re
import hashlib
from typing import List, Dict, Optional

# ---- 术语表：英文→中文权威译名 ----
GLOSSARY: Dict[str, str] = {
    # 罗马/拜占庭
    "Byzantine Empire": "拜占庭帝国",
    "Byzantine": "拜占庭",
    "Constantinople": "君士坦丁堡",
    "Justinian": "查士丁尼",
    "Theodora": "狄奥多拉",
    "Belisarius": "贝利撒留",
    "Narses": "纳尔塞斯",
    "Heraclius": "希拉克略",
    "Basileus": "巴西琉斯（皇帝）",
    "Augustus": "奥古斯都",
    "Caesar": "凯撒",
    # 政治/制度
    "Senate": "元老院",
    "Consul": "执政官",
    "Praetorian Guard": "近卫军",
    "Praetorian Prefect": "近卫军长官",
    "Magister Militum": "军事长官",
    "Patriarch": "牧首",
    "Ecumenical Council": "大公会议",
    "Arianism": "阿里乌主义",
    "Monophysitism": "一性论",
    "Orthodoxy": "正教",
    # 历史事件
    "Council of Nicaea": "尼西亚会议",
    "Edict of Milan": "米兰敕令",
    "Fall of the Western Roman Empire": "西罗马帝国灭亡",
    "Nika Riots": "尼卡暴动",
    "Plague of Justinian": "查士丁尼瘟疫",
    # 军事
    "Legion": "军团",
    "Cataphract": "具装骑兵",
    "Foederati": "同盟者（蛮盟部队）",
    "Limitanei": "边防军",
    "Comitatenses": "野战军",
    # 学术
    "Late Antiquity": "古代晚期",
    "Dark Ages": "黑暗时代",
    "Pax Romana": "罗马和平",
    "Tetrarchy": "四帝共治制",
    "Dominate": "多米纳特制（君主专制）",
    "Principate": "元首制",
}

# ---- 后处理规则：正则替换 ----
POST_RULES: List[tuple] = [
    # 修复常见翻译错误
    (r'(?<![a-zA-Z])I\b(?![a-zA-Z])', '我'),       # 英文 I → 中文 我（仅当孤立出现）
    (r'(\d+)\s*BC', r'公元前\1年'),                   # 年份规范
    (r'(\d+)\s*AD', r'公元\1年'),
    # 修复标点
    (r'\s*,\s*', '，'),                                # 英文逗号 → 中文逗号
    (r'\s*\.\s*$', '。'),                              # 句尾英文句号 → 中文句号
    # 书名号
    (r'《\s*', '《'),                                   # 去空格
    (r'\s*》', '》'),
]


def apply_glossary(text: str) -> str:
    """术语表后处理：将英文术语/人名替换为权威中文译名"""
    for en, zh in GLOSSARY.items():
        if en in text:
            text = text.replace(en, zh)
    return text


def apply_post_rules(text: str) -> str:
    """后处理规则：修复常见翻译错误、标点规范"""
    for pattern, replacement in POST_RULES:
        text = re.sub(pattern, replacement, text)
    return text


def enhance_translation(text: str) -> str:
    """综合翻译增强：术语表 → 后处理规则"""
    text = apply_glossary(text)
    text = apply_post_rules(text)
    return text


# ---- Token 优化：上下文截断 ----
def truncate_tm_context(matches: List[Dict], max_items: int = 2, max_chars: int = 300) -> str:
    """截断翻译记忆上下文，控制 Token 消耗

    Args:
        matches: TM 匹配结果列表
        max_items: 最多引用 N 条
        max_chars: 每条原文+译文最多字符数
    """
    if not matches:
        return ""

    items = matches[:max_items]
    parts = []
    for i, m in enumerate(items):
        src = m['source'][:max_chars]
        tgt = m['target'][:max_chars]
        parts.append(f"参考 {i+1}:\n原文: {src}\n译文: {tgt}")
    return "\n".join(parts)


def truncate_rag_context(items: List[Dict], max_items: int = 2, max_chars: int = 400) -> str:
    """截断知识库上下文"""
    if not items:
        return ""
    parts = []
    for item in items[:max_items]:
        doc = item['document'][:max_chars]
        parts.append(f"[{item['kb_name']}] {doc}")
    return "\n".join(parts)


# ---- 输入缓存（避免重复 API 调用） ----
_cache: Dict[str, str] = {}

def cache_key(text: str, tm_count: int, kb_count: int) -> str:
    """生成缓存键"""
    raw = f"{text}|tm={tm_count}|kb={kb_count}"
    return hashlib.md5(raw.encode()).hexdigest()

def get_cached(key: str) -> Optional[str]:
    return _cache.get(key)

def set_cache(key: str, value: str):
    _cache[key] = value
    # 限制缓存大小
    if len(_cache) > 500:
        # 删除最早的一半
        for k in list(_cache.keys())[:250]:
            del _cache[k]
