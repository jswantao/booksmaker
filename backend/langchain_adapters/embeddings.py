# langchain_adapters/embeddings.py — QoderWorkEmbeddings
#
# 把项目现有的 EmbeddingManager 单例包装为 LangChain Embeddings 接口，
# 让 VectorStore / Retriever 链能调用。底层 BGE/OpenAI 加载、查询前缀、
# 维度检测 等逻辑全部保留。

from __future__ import annotations

from typing import List

from langchain_core.embeddings import Embeddings


class QoderWorkEmbeddings(Embeddings):
    """Embeddings 适配器：转发到项目内部 EmbeddingManager 单例。

    用法:
        emb = QoderWorkEmbeddings()
        vecs = emb.embed_documents(["hello", "world"])
        qvec = emb.embed_query("hello")

    说明：
    - 本项目 EmbeddingManager.embed(texts, is_query=...) 在 is_query=True 时
      会自动给 BGE 文本加查询前缀，所以 embed_documents / embed_query 必须
      分别传 is_query=False / True 以维持语义检索精度。
    - 每次调用都重新获取 EmbeddingManager() 单例，避免持有过期引用。
    """

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        from embedding_providers import EmbeddingManager

        manager = EmbeddingManager()
        return manager.embed(texts, is_query=False)

    def embed_query(self, text: str) -> List[float]:
        from embedding_providers import EmbeddingManager

        manager = EmbeddingManager()
        vecs = manager.embed([text], is_query=True)
        if not vecs:
            raise RuntimeError("EmbeddingManager returned empty vector for query")
        return vecs[0]
