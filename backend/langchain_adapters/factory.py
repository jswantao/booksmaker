# langchain_adapters/factory.py — 工厂函数
#
# LCEL / Agent 链通过工厂取模型与嵌入，不直接 import LLMManager / EmbeddingManager，
# 便于未来切换实现或加 A/B 测试逻辑。

from __future__ import annotations

from typing import Optional

from langchain_adapters.chat_models import ChatQoderWork
from langchain_adapters.embeddings import QoderWorkEmbeddings

# Agent task name → LLMManager slot name.
# LLMManager 的 provider 字典使用较短的 slot 名（translate / epub / default），
# 而 agent / model_router / LCEL prompt 使用较长的描述性名称。
# 工厂函数统一转换，确保 ChatQoderWork.task 命中正确的 provider slot。
_AGENT_TASK_TO_LLM_SLOT = {
    "paragraph_translate": "translate",
    "long_text_translate": "translate",
    "epub_replace": "epub",
    "kb_build": "default",
    "term_extract": "default",
}


def get_chat_model(
    task: str = "default",
    model_name: Optional[str] = None,
    streaming: bool = True,
) -> ChatQoderWork:
    """根据 task 返回包装好的 ChatQoderWork 实例。

    Args:
        task: Agent task name (paragraph_translate / epub_replace / kb_build /
              long_text_translate / term_extract) 或 LLMManager slot name
              (translate / epub / default)。工厂自动把 agent name 映射到 slot。
        model_name: 显示用，不影响实际模型选择（由 LLMManager 单例决定）
        streaming: 默认是否走流式路径（LCEL 链也可单独 .stream()）
    """
    llm_slot = _AGENT_TASK_TO_LLM_SLOT.get(task, task)
    return ChatQoderWork(
        task=llm_slot,
        model_name=model_name or f"qoderwork:{task}",
        streaming=streaming,
    )


def get_embeddings() -> QoderWorkEmbeddings:
    """返回包装好的 QoderWorkEmbeddings 单例（每次都新建，但底层 EmbeddingManager 是单例）。"""
    return QoderWorkEmbeddings()
