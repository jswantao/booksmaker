# services/translate_optimizer.py — 翻译增强：术语表 + 后处理 + 上下文截断
"""提供术语表替换、后处理规则、上下文Token优化"""

import re
import hashlib
from typing import List, Dict, Optional

# ---- 种子术语表：用于初始化新记忆库，运行时优先使用记忆库动态术语 ----
SEED_GLOSSARY: Dict[str, str] = {
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


def apply_glossary(text: str, glossary: Dict[str, str] = None) -> str:
    """术语表后处理：优先使用动态术语表（记忆库），回退到种子术语表"""
    target = glossary if glossary else SEED_GLOSSARY
    for en, zh in target.items():
        if en in text:
            text = text.replace(en, zh)
    return text


def apply_post_rules(text: str) -> str:
    """后处理规则：修复常见翻译错误、标点规范"""
    for pattern, replacement in POST_RULES:
        text = re.sub(pattern, replacement, text)
    return text


# ---- 评论段落检测与截断 ----
# Qwen 等模型有时会在译文后追加评论性总结、名词解释、术语附录等
# 精简至 8 个高准确率核心模式，移除过于宽泛可能误伤正文的 pattern
_COMMENTARY_PATTERNS = [
    # === 高准确率评论/总结类（4个）===
    r'^这段(?:历史)?(?:文字|文本|话|内容|段落|文章)(?:主要)?(?:讲述|描述|介绍|讨论|说明|记载)',
    r'^(?:总的来看|总体而言|综上所述|概括而言)',
    r'^(?:总结|评论|分析|解读|小结)[：:\s]',
    r'^(?:本文|此文|原文)(?:通过|主要|旨在)',
    # === 名词解释/术语附录类（2个）===
    r'^(?:名词|术语|词汇|关键词)(?:解释|说明|注[释解]|列表|对照)',
    r'^(?:注[：:\s]|译注[：:\s]|备注[：:\s])',
    # === 列表式术语附录（2个）===
    r'^[-*]\s*"[^"]{1,40}"\s*[：:]\s*(?:在|指|是|意为)',
    r'^[-*]\s*\*\*[^*]+\*\*\s*[：:]\s*(?:在|指|是|意为|表示)',
]


def strip_commentary(text: str) -> str:
    """检测并删除译文末尾的评论/总结/名词解释段落。

    Qwen 等指令微调模型在翻译时偶尔会追加：
    - "这段文字讲述了..."式的段落总结
    - "请注意，这段文本中包含了一些需要额外解释的名词"式的名词附录
    - "- \"term\"：..."式的术语对照列表

    策略（双重扫描）：
    第一遍：按段落扫描，匹配评论模式 → 截断
    第二遍：按行扫描，检测列表式术语附录 → 截断
    """
    result = text.strip()

    # ====== 第一遍：段落级扫描 ======
    paragraphs = re.split(r'\n\s*\n', result)
    if len(paragraphs) > 1:
        clean_paragraphs = []
        stopped = False
        for para in paragraphs:
            para_stripped = para.strip()
            if not para_stripped:
                clean_paragraphs.append(para)
                continue
            for pattern in _COMMENTARY_PATTERNS:
                if re.match(pattern, para_stripped):
                    print(f"[Optimizer] Stripped paragraph: {para_stripped[:80]}...")
                    stopped = True
                    break
            if stopped:
                break
            clean_paragraphs.append(para)
        if stopped:
            result = '\n\n'.join(clean_paragraphs).strip()

    # ====== 第二遍：行级扫描（检测列表式术语附录） ======
    lines = result.split('\n')
    # 从后往前找到第一个疑似术语附录的行
    glossary_start = -1
    glossary_pattern = re.compile(
        r'^\s*[-*]\s*"[^"]{1,40}"\s*[：:]\s*(?:在|指|是|意为|指代|这里|用于|表示)'
    )
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if glossary_pattern.match(line):
            glossary_start = i
            print(f"[Optimizer] Stripped glossary line: {line[:80]}...")
        elif glossary_start > 0 and line and not glossary_pattern.match(line):
            # 遇到非术语行的正文内容，停止回溯
            break

    if glossary_start > 0:
        # 确保截断点在正文结束处（空行后）
        cut = glossary_start
        while cut > 0 and not lines[cut - 1].strip():
            cut -= 1
        result = '\n'.join(lines[:cut]).strip()

    return result if result else text.strip()


def enhance_translation(text: str, glossary: Dict[str, str] = None) -> str:
    """综合翻译增强：评论截断 → 术语表（动态） → 后处理规则"""
    text = strip_commentary(text)  # 第一步：截断评论
    text = apply_glossary(text, glossary)
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

def cache_key(text: str, tm_count: int, kb_count: int, mem_count: int = 0) -> str:
    """生成缓存键（含记忆库术语数，术语变化后缓存自动失效）"""
    raw = f"{text}|tm={tm_count}|kb={kb_count}|mem={mem_count}"
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
