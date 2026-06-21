# services/context_budget.py — 统一的上下文预算管理
# 协调 TM / RAG / 记忆库 / System Prompt 的字符预算分配
# 替代之前分散在 translate_optimizer / translation_pipeline / model_providers 中的独立截断逻辑

from typing import Dict, Optional


class ContextBudget:
    """统一上下文预算：以字符为单位，按比例分配给各上下文组件。

    预算分配策略：
    - System Prompt 和 User Text 是硬需求，先扣除
    - 剩余空间按比例分配：TM 1/3, RAG 1/3, 记忆库 1/6, 余量 1/6
    - 每部分有上下限，防止极端情况
    """

    # 各组件的字符上下限
    LIMITS = {
        "tm_budget":     (200, 800),
        "rag_budget":    (200, 1000),
        "memory_budget": (200, 500),
    }

    def __init__(self, max_chars: int = 8000, reserved_for_output: int = 2000):
        """
        Args:
            max_chars: 模型最大输入容量（字符数）。
                       本地 7B 模型约 6000-8000 字符安全区；
                       云端 API 可设为更高值。
            reserved_for_output: 预留给模型输出的字符数
        """
        self.max_chars = max_chars
        self.reserved = reserved_for_output
        self.available = max_chars - reserved_for_output

    def allocate(self, system_prompt: str, user_text: str) -> Dict[str, int]:
        """计算各部分的字符预算

        Args:
            system_prompt: 系统提示词（含翻译原则等）
            user_text: 待翻译的原文

        Returns:
            dict: {"tm_budget": int, "rag_budget": int, "memory_budget": int}
        """
        sys_len = len(system_prompt)
        user_len = len(user_text)
        remaining = self.available - sys_len - user_len

        if remaining < 300:
            # 极端情况：原文+系统提示已占满，给最小预算
            return {"tm_budget": 100, "rag_budget": 100, "memory_budget": 100}

        # 按比例分配
        raw = {
            "tm_budget": remaining // 3,
            "rag_budget": remaining // 3,
            "memory_budget": remaining // 6,
        }

        # 裁剪到上下限
        result = {}
        for key, (lo, hi) in self.LIMITS.items():
            result[key] = max(lo, min(raw.get(key, lo), hi))

        return result

    def truncate_with_budget(self, parts: Dict[str, str],
                             budget: Dict[str, int]) -> Dict[str, str]:
        """根据预算截断各部分内容（头保留优先）

        Args:
            parts: {"tm_context": str, "rag_context": str, "memory_context": str}
            budget: allocate() 的返回值

        Returns:
            截断后的各部分内容
        """
        key_map = {
            "tm_context": "tm_budget",
            "rag_context": "rag_budget",
            "memory_context": "memory_budget",
        }
        result = {}
        for part_key, budget_key in key_map.items():
            text = parts.get(part_key, "")
            limit = budget.get(budget_key, 300)
            if len(text) > limit:
                result[part_key] = text[:limit - 30] + "\n... [上下文已截断]"
            else:
                result[part_key] = text
        return result

    def build_safety_net(self, total_prompt: str, hard_limit: int = 0) -> str:
        """最终安全网：如果总 prompt 仍超过硬限制，做首尾拼接截断。
        这是最后一道防线，正常情况下不应触发。

        Args:
            total_prompt: 拼接后的完整 prompt
            hard_limit: 硬限制字符数（0=使用 self.available）
        """
        limit = hard_limit or self.available
        if len(total_prompt) <= limit:
            return total_prompt

        # 保留首部 40% 和尾部 50%，中间截断
        head = int(limit * 0.4)
        tail = int(limit * 0.5)
        return (total_prompt[:head]
                + "\n\n... [中间参考上下文已截断] ...\n\n"
                + total_prompt[-tail:])


# 默认实例（适用于大多数本地 7B 模型）
default_budget = ContextBudget(max_chars=8000, reserved_for_output=2000)

# 云端 API 实例（更大上下文窗口）
cloud_budget = ContextBudget(max_chars=30000, reserved_for_output=4000)
