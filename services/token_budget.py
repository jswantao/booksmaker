# services/token_budget.py — Token 预算管理
"""Token 估算与自动截断，适用于云端 API 模式控制成本。

用法:
    budget = TokenBudget(max_tokens=4000)
    messages = budget.fit(messages)
    # messages 已被截断到预算内
"""

from typing import List, Dict, Optional


class TokenBudget:
    """Token 预算管理器：估算 + 自动截断"""

    # 粗略估算: 中文 ~1.5 token/字, 英文 ~1.3 token/字, 代码 ~1.0 token/字
    # 保守取 2.0，确保不超
    CHARS_PER_TOKEN = 2.0

    def __init__(self, max_tokens: int = 4000, reserve_for_output: int = 2048):
        """
        Args:
            max_tokens: 总 Token 预算上限
            reserve_for_output: 预留给模型输出的 Token 数
        """
        self.max_tokens = max_tokens
        self.reserve = reserve_for_output
        self.input_budget = max_tokens - reserve_for_output

    def estimate(self, text: str) -> int:
        """估算文本 Token 数（字符数/2 保守估算）"""
        return max(1, int(len(text) / self.CHARS_PER_TOKEN))

    def estimate_messages(self, messages: List[Dict[str, str]]) -> int:
        """估算整个 messages 列表的 Token 数"""
        total = 0
        for msg in messages:
            total += self.estimate(msg.get("content", ""))
            total += 4  # role + 格式开销
        return total

    def _truncate_text(self, text: str, max_tokens: int) -> str:
        """截断文本到指定 token 数以内，在句子边界处截断"""
        max_chars = int(max_tokens * self.CHARS_PER_TOKEN)
        if len(text) <= max_chars:
            return text

        # 在 max_chars 附近找最近的句子边界
        truncated = text[:max_chars]
        # 找最后一个句号、换行或空格
        boundaries = ['. ', '.\n', '\n\n', '\n', '。', '；', '  ']
        best_pos = max_chars
        for boundary in boundaries:
            pos = truncated.rfind(boundary)
            if pos > max_chars * 0.5:
                best_pos = min(best_pos, pos + len(boundary))
                break

        return truncated[:best_pos].rstrip() + "\n... [Token预算截断]"

    def fit(self, messages: List[Dict[str, str]],
            preserve_first: int = 1, preserve_last: int = 1) -> List[Dict[str, str]]:
        """调整 messages 使其总 Token 数不超过预算。

        策略：
        - 保留前 preserve_first 条不动（通常是 system prompt）
        - 保留后 preserve_last 条不动（通常是 user message）
        - 中间的消息按优先级截断

        Args:
            messages: OpenAI 格式消息列表
            preserve_first: 开头保留条数
            preserve_last: 末尾保留条数

        Returns:
            截断后的消息列表
        """
        total = self.estimate_messages(messages)
        if total <= self.input_budget:
            return messages  # 不需要截断

        # 前 preserve_first 条不可截断
        head = messages[:preserve_first]
        tail = messages[-preserve_last:] if preserve_last > 0 else []
        middle = messages[preserve_first:len(messages) - preserve_last] if preserve_last > 0 else messages[preserve_first:]

        # 计算已占用的 token
        head_tokens = self.estimate_messages(head)
        tail_tokens = self.estimate_messages(tail)

        # 中间部分可用预算
        budget_for_middle = self.input_budget - head_tokens - tail_tokens
        if budget_for_middle <= 0:
            # 预算不足，只保留 head + tail
            print(f"[TokenBudget] Budget tight: head={head_tokens}, tail={tail_tokens}, dropping middle entirely")
            return head + tail

        # 对 middle 中的每条消息做截断
        # 平均分配预算
        per_msg_budget = max(100, budget_for_middle // len(middle)) if middle else 0
        result = list(head)
        for msg in middle:
            content = msg.get("content", "")
            if self.estimate(content) > per_msg_budget:
                msg = dict(msg)
                msg["content"] = self._truncate_text(content, per_msg_budget)
            result.append(msg)
        result.extend(tail)

        new_total = self.estimate_messages(result)
        print(f"[TokenBudget] Fitted: {total} → {new_total} tokens "
              f"(budget={self.input_budget}, saved={total - new_total})")
        return result

    def should_use_cache(self, messages: List[Dict[str, str]], cache_ratio: float = 0.6) -> bool:
        """判断是否应该优先使用缓存（高 token 消耗时建议缓存）"""
        return self.estimate_messages(messages) > self.input_budget * cache_ratio


def get_budget_for_provider(llm_provider: str, model_name: str = "") -> TokenBudget:
    """根据 LLM 提供者返回合适的 Token 预算

    - 本地模型：宽松预算 (8000 input + 2048 output)
    - 云端 API：紧凑预算 (4000 input + 2048 output)
    """
    if llm_provider == "local":
        return TokenBudget(max_tokens=10000, reserve_for_output=2048)
    else:
        # OpenAI/其他 API：控制成本
        if "gpt-4" in model_name.lower():
            return TokenBudget(max_tokens=8000, reserve_for_output=2048)
        return TokenBudget(max_tokens=4000, reserve_for_output=2048)
