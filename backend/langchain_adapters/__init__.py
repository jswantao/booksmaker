# langchain_adapters/__init__.py — LangChain 集成适配器包
#
# 把项目现有的 LLMManager / EmbeddingManager 包装为 LangChain 标准接口，
# 供 LCEL 链、Agent 框架、Retriever 框架使用，而不改动底层实现。
#
# 主要导出:
#   - ChatQoderWork: BaseChatModel 适配器，转发到 LLMManager
#   - QoderWorkEmbeddings: Embeddings 适配器，转发到 EmbeddingManager
#   - get_chat_model(task): 工厂函数
#   - get_embeddings(): 工厂函数

from langchain_adapters.chat_models import ChatQoderWork
from langchain_adapters.embeddings import QoderWorkEmbeddings
from langchain_adapters.factory import get_chat_model, get_embeddings

__all__ = [
    "ChatQoderWork",
    "QoderWorkEmbeddings",
    "get_chat_model",
    "get_embeddings",
]
