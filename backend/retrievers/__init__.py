# retrievers/ -- LangChain-compatible retriever adapters
#
# QoderWorkBM25Retriever: BM25Okapi + jieba keyword search over ChromaDB collections
# HybridRetriever: vector (Chroma) + BM25 with RRF fusion + optional CrossEncoder rerank

from retrievers.bm25 import QoderWorkBM25Retriever
from retrievers.hybrid import HybridRetriever

__all__ = ["QoderWorkBM25Retriever", "HybridRetriever"]
