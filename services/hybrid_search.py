# services/hybrid_search.py — 混合检索（向量 + 全文 + 重排序）
"""参考 Dify 知识库方案：同时执行语义检索和关键词检索，加权重排序"""

import hashlib
import re
from typing import List, Dict, Optional
from embedding_providers import EmbeddingManager
from core.database import chroma_client
from config import user_api_config


class HybridSearcher:
    """混合检索器：向量语义 + 全文关键词，加权重排序"""

    _defaults = {
        "top_k": 3,
        "score_threshold": 0.3,
        "semantic_weight": 0.7,
        "keyword_weight": 0.3,
    }

    def __init__(self, top_k: int = None, score_threshold: float = None,
                 semantic_weight: float = None, keyword_weight: float = None):
        self.top_k = top_k or self._defaults["top_k"]
        self.score_threshold = score_threshold or self._defaults["score_threshold"]
        self.semantic_weight = semantic_weight if semantic_weight is not None else self._defaults["semantic_weight"]
        self.keyword_weight = keyword_weight if keyword_weight is not None else self._defaults["keyword_weight"]

        # 归一化权重
        total = self.semantic_weight + self.keyword_weight
        if total > 0:
            self.semantic_weight /= total
            self.keyword_weight /= total

    # ---- 全文检索 ----
    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """中文/英文分词（简易版，生产环境可替换为 jieba）"""
        # 中文字符单字切分 + 英文单词
        tokens = []
        # 匹配中文连续块或英文单词
        for match in re.finditer(r'[一-鿿]+|[a-zA-Z]+|\d+', text.lower()):
            word = match.group()
            if re.match(r'[一-鿿]+', word):
                # 中文：2-gram 分词
                if len(word) <= 2:
                    tokens.append(word)
                else:
                    for i in range(len(word) - 1):
                        tokens.append(word[i:i + 2])
            else:
                tokens.append(word)
        return tokens

    @staticmethod
    def _keyword_score(query_tokens: List[str], doc: str) -> float:
        """计算关键词匹配分数（TF-IDF 简化版）"""
        if not query_tokens or not doc:
            return 0.0
        doc_lower = doc.lower()
        # 计算命中数
        hits = sum(1 for t in query_tokens if t in doc_lower)
        if hits == 0:
            return 0.0
        # TF 因子：命中 tokens 在文档中出现的频率
        tf = hits / max(len(query_tokens), 1)
        # 位置奖励：越靠前权重越高
        positions = [doc_lower.find(t) for t in query_tokens if t in doc_lower]
        pos_bonus = 1.0 - (min(positions) / max(len(doc_lower), 1)) if positions else 0
        return min(tf * (0.7 + 0.3 * pos_bonus), 1.0)

    def keyword_search(self, collection_name: str, query: str, n_results: int = 10) -> List[Dict]:
        """全文关键词检索"""
        try:
            collection = chroma_client.get_collection(collection_name)
            all_docs = collection.get(limit=1000)
        except Exception:
            return []

        if not all_docs.get('documents'):
            return []

        query_tokens = self._tokenize(query)
        results = []
        for i, doc in enumerate(all_docs['documents']):
            score = self._keyword_score(query_tokens, doc)
            if score > 0:
                results.append({"document": doc, "score": round(score, 4), "method": "keyword",
                                "metadata": all_docs.get('metadatas', [{}])[i] if i < len(
                                    all_docs.get('metadatas', [])) else {}})
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:n_results]

    def vector_search(self, collection_name: str, query: str, n_results: int = 10) -> List[Dict]:
        """向量语义检索"""
        if user_api_config.get("embedding_provider") != "bge" and not user_api_config.get("api_key"):
            return []
        try:
            collection = chroma_client.get_collection(collection_name)
            q_emb = EmbeddingManager().embed([query], is_query=True)[0]
            resp = collection.query(query_embeddings=[q_emb], n_results=n_results)
        except Exception:
            return []

        if not resp.get('ids') or not resp['ids'][0]:
            return []

        results = []
        for i in range(len(resp['ids'][0])):
            dist = resp['distances'][0][i] if resp.get('distances') else 0
            sim = 1.0 - min(dist, 1.0)
            if sim >= self.score_threshold:
                results.append({"document": resp['documents'][0][i], "score": round(sim, 4),
                                "method": "vector",
                                "metadata": resp.get('metadatas', [[]])[0][i] if i < len(
                                    resp.get('metadatas', [[]])[0]) else {}})
        return results

    def search(self, collection_name: str, query: str) -> List[Dict]:
        """混合检索：融合向量和关键词结果，加权重排序

        Args:
            collection_name: ChromaDB 集合名
            query: 搜索查询文本

        Returns:
            [{"document": str, "score": float, "method": str}, ...] 按最终分数降序
        """
        # 1. 同时执行两种检索
        vector_results = []
        keyword_results = []

        # 语义权重 > 0 时执行向量检索
        if self.semantic_weight > 0:
            vector_results = self.vector_search(collection_name, query, self.top_k * 3)

        # 关键词权重 > 0 时执行全文检索
        if self.keyword_weight > 0:
            keyword_results = self.keyword_search(collection_name, query, self.top_k * 3)

        # 2. 合并并加权重排序
        merged: Dict[str, Dict] = {}  # doc_hash → result

        for r in vector_results:
            h = hashlib.md5(r['document'].encode()).hexdigest()
            merged[h] = {"document": r['document'], "score": r['score'] * self.semantic_weight,
                         "scores": {"vector": r['score'], "keyword": 0.0},
                         "methods": ["vector"], "metadata": r.get('metadata', {})}

        for r in keyword_results:
            h = hashlib.md5(r['document'].encode()).hexdigest()
            kw_score = r['score'] * self.keyword_weight
            if h in merged:
                merged[h]['score'] += kw_score
                merged[h]['scores']['keyword'] = r['score']
                merged[h]['methods'].append('keyword')
            else:
                merged[h] = {"document": r['document'], "score": kw_score,
                             "scores": {"vector": 0.0, "keyword": r['score']},
                             "methods": ["keyword"], "metadata": r.get('metadata', {})}

        # 3. 按最终分数排序 + 阈值过滤
        results = sorted(merged.values(), key=lambda x: x['score'], reverse=True)
        results = [r for r in results if r['score'] >= self.score_threshold]

        # 只返回简洁结果
        return [{"document": r['document'], "score": r['score'], "method": "+".join(r['methods']),
                 "detail": r.get('scores', {})} for r in results[:self.top_k]]


# ---- 多知识库混合检索 ----
def hybrid_query_multiple(kb_ids: List[str], query: str, **searcher_kwargs) -> List[Dict]:
    """跨多个 KB 的混合检索"""
    from services.knowledge_manager import kb_manager

    if not kb_ids:
        return []

    kbs = kb_manager.get_kbs_by_ids(kb_ids)
    if not kbs:
        return []

    searcher = HybridSearcher(**searcher_kwargs)
    all_results = []
    seen = set()

    for kb in kbs:
        try:
            results = searcher.search(kb['collection_name'], query)
            for r in results:
                h = hashlib.md5(r['document'].encode()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    r['kb_id'] = kb['id']
                    r['kb_name'] = kb['name']
                    all_results.append(r)
        except Exception as e:
            print(f"Hybrid search failed for KB {kb['name']}: {e}")

    all_results.sort(key=lambda x: x['score'], reverse=True)
    return all_results[:searcher.top_k]


# ---- 分组加权混合检索 ----
class GroupedHybridSearcher:
    """按分组精准调用知识库，每组独立权重/top_k/阈值。

    用法示例：
        groups = {
            "terminology": {"kb_ids": [...], "weight": 1.2, "top_k": 3, "threshold": 0.5},
            "background":  {"kb_ids": [...], "weight": 0.8, "top_k": 2, "threshold": 0.3},
        }
        searcher = GroupedHybridSearcher(groups)
        results = searcher.search(query)            # 搜全部分组
        results = searcher.search(query, "terminology")  # 只搜术语组
    """

    def __init__(self, kb_groups: Dict[str, Dict]):
        self.groups = kb_groups

    def _search_group(self, query: str, group_cfg: Dict) -> List[Dict]:
        """搜索单个分组"""
        from services.knowledge_manager import kb_manager

        kb_ids = group_cfg.get("kb_ids", [])
        top_k = group_cfg.get("top_k", 2)
        threshold = group_cfg.get("threshold", 0.3)
        sem_w = group_cfg.get("semantic_weight", 0.7)
        kw_w = group_cfg.get("keyword_weight", 0.3)

        if not kb_ids:
            return []

        return hybrid_query_multiple(
            kb_ids, query,
            top_k=top_k,
            score_threshold=threshold,
            semantic_weight=sem_w,
            keyword_weight=kw_w,
        )

    def search(self, query: str, group_name: str = None) -> List[Dict]:
        """搜索知识库

        Args:
            query: 查询文本
            group_name: 指定分组名称。None 时搜索所有分组并加权合并。

        Returns:
            去重排序后的结果列表
        """
        if group_name:
            group = self.groups.get(group_name)
            if not group:
                return []
            results = self._search_group(query, group)
            for r in results:
                r["group"] = group_name
            return results

        # 搜索所有分组，加权合并
        all_results = []
        seen = set()

        for name, group_cfg in self.groups.items():
            weight = group_cfg.get("weight", 1.0)
            results = self._search_group(query, group_cfg)

            for r in results:
                h = hashlib.md5(r.get('document', '').encode()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    r["group"] = name
                    r["score"] *= weight  # 分组加权
                    all_results.append(r)

        all_results.sort(key=lambda x: x["score"], reverse=True)
        return self._deduplicate(all_results)[:5]

    @staticmethod
    def _deduplicate(results: List[Dict]) -> List[Dict]:
        """按文档内容去重，保留分数最高的"""
        seen = set()
        unique = []
        for r in results:
            h = hashlib.md5(r.get('document', '').encode()).hexdigest()
            if h not in seen:
                seen.add(h)
                unique.append(r)
        return unique
