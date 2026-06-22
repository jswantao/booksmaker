# services/model_capabilities.py — 模型能力声明
#
# 用于 LCEL chain 在构建时判断当前模型是否支持 function calling / tool binding。
# 不支持的模型走 prompt 注入路径（把工具查询结果预填到 prompt 里），
# 支持的模型可额外启用 bind_tools 让 LLM 主动调用。

from __future__ import annotations

from typing import Dict


# 显式声明支持 tool calling 的模型家族 / ID 关键字。
# 匹配规则：model_name 小写后包含任一关键字即视为支持。
_TOOL_CALLING_KEYWORDS = (
    # OpenAI 全系列
    "gpt-4", "gpt-3.5", "gpt-4o", "o1", "o3",
    # Anthropic
    "claude",
    # Qwen 2.5+ Instruct 系列（注意 Qwen2-7B 等非 .5 版本不支持）
    "qwen2.5", "qwen3", "qwen3.5",
    # GLM 3+
    "glm-4",
    # DeepSeek
    "deepseek-chat", "deepseek-coder",
)


# 显式黑名单：即使关键字命中上面，也不支持 tool calling
_TOOL_CALLING_DENY_KEYWORDS = (
    "qwen2-7b", "qwen2-1.5b", "qwen2-0.5b",  # Qwen2（不带 .5）不支持
    "hy-mt",                                   # Hunyuan-MT 翻译模型不支持
    "bloom", "mt5", "marian", "nllb",          # 老一代翻译模型
)


def supports_tool_calling(model_name: str) -> bool:
    """判断给定 model_name 是否支持 LangChain bind_tools / function calling。"""
    if not model_name:
        return False
    low = model_name.lower()

    if any(k in low for k in _TOOL_CALLING_DENY_KEYWORDS):
        return False
    return any(k in low for k in _TOOL_CALLING_KEYWORDS)


# 模型家族 → 推荐 system prompt 风格（用于 Phase 2.5 中动态选 chat template）
# 当前只记录，未消费；留给后续优化。
MODEL_FAMILY_HINTS: Dict[str, str] = {
    "qwen": "chatml",
    "hunyuan": "hunyuan",
    "llama": "llama3",
    "gpt": "openai",
    "claude": "anthropic",
}
