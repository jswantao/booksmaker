# services/hybrid_search.py — Hybrid index model (Dify-style)
# keyword + semantic + rerank, scoped to group/chapter only

import hashlib
import re
from typing import List, Dict, Optional

from embedding_providers import EmbeddingManager
from core.database import chroma_client
from config import user_api_config

class HybridSearcher:
    """Dify-style hybrid: vector + BM25-like keyword + rerank, scoped"""

    def __init__(self, top_k: int = 3, score_threshold: float = 0.35,
                 semantic_weight: float = 0.6, keyword_weight: float = 0.4):
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        # normalize
        total = semantic_weight + keyword_weight
        if total > 0:
            self.semantic_weight /= total
            self.keyword_weight /= total

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        tokens = []
        for m in re.finditer(r'[一-鿿]+|[a-zA-Z]+|\d+', text.lower()):
            w = m.group()
            if re.match(r'[一-鿿]+', w):
                if len(w) <= 2:
                    tokens.append(w)
                else:
                    for i in range(len(w)-1):
                        tokens.append(w[i:i+2])
            else:
                tokens.append(w)
        return tokens

    @staticmethod
    def _bm25_score(query_tokens: List[str], doc: str) -> float:
        if not query_tokens or not doc: return 0.0
        dl = doc.lower()
        hits = sum(1 for t in query_tokens if t in dl)
        if hits == 0: return 0.0
        tf = hits / len(query_tokens)
        # position boost
        positions = [dl.find(t) for t in query_tokens if t in dl]
        pos_bonus = 1.0 - (min(positions) / max(len(dl),1)) if positions else 0
        return min(tf * (0.65 + 0.35*pos_bonus), 1.0)

    def _vector_search_scoped(self, collection_name: str, query: str, n_results: int,
                              where_filter: Optional[Dict] = None) -> List[Dict]:
        if user_api_config.get("embedding_provider") != "bge" and not user_api_config.get("api_key"):
            return []
        try:
            col = chroma_client.get_collection(collection_name)
            q_emb = EmbeddingManager().embed([query], is_query=True)[0]
            kwargs = {"query_embeddings": [q_emb], "n_results": n_results}
            if where_filter:
                kwargs["where"] = where_filter
            resp = col.query(**kwargs)
        except Exception:
            return []
        if not resp.get('ids') or not resp['ids'][0]:
            return []
        out = []
        for i in range(len(resp['ids'][0])):
            dist = resp['distances'][0][i] if resp.get('distances') else 0
            sim = 1.0 - min(dist, 1.0)
            if sim >= self.score_threshold:
                meta = resp.get('metadatas', [[]])[0][i] if resp.get('metadatas') else {}
                out.append({
                    "document": resp['documents'][0][i],
                    "score": round(sim,4),
                    "method": "vector",
                    "metadata": meta
                })
        return out

    def _keyword_search_scoped(self, collection_name: str, query: str, n_results: int,
                               where_filter: Optional[Dict] = None) -> List[Dict]:
        try:
            col = chroma_client.get_collection(collection_name)
            # Chroma where filter for keyword prefetch
            if where_filter:
                all_docs = col.get(where=where_filter, limit=2000)
            else:
                all_docs = col.get(limit=1500)
        except Exception:
            return []
        if not all_docs.get('documents'): return []
        qt = self._tokenize(query)
        res = []
        docs = all_docs['documents']
        metas = all_docs.get('metadatas', [{}]*len(docs))
        for i, doc in enumerate(docs):
            sc = self._bm25_score(qt, doc)
            if sc > 0:
                res.append({"document": doc, "score": round(sc,4), "method": "keyword", "metadata": metas[i] if i < len(metas) else {}})
        res.sort(key=lambda x: x['score'], reverse=True)
        return res[:n_results]

    def search(self, collection_name: str, query: str,
               group: Optional[str] = None,
               chapter: Optional[str] = None) -> List[Dict]:
        """
        Dify hybrid: scoped to group/chapter ONLY, not entire KB.
        where_filter ensures retrieval must use only the relevant group/chapter content.
        """
        where_filter = None
        if group or chapter:
            where_filter = {}
            if group: where_filter["group"] = group
            if chapter: where_filter["chapter"] = chapter

        vector_results = self._vector_search_scoped(collection_name, query, self.top_k*3, where_filter) if self.semantic_weight>0 else []
        keyword_results = self._keyword_search_scoped(collection_name, query, self.top_k*3, where_filter) if self.keyword_weight>0 else []

        merged: Dict[str, Dict] = {}
        for r in vector_results:
            h = hashlib.md5(r['document'].encode()).hexdigest()
            merged[h] = {
                "document": r['document'],
                "score": r['score'] * self.semantic_weight,
                "scores": {"vector": r['score'], "keyword": 0.0},
                "methods": ["vector"],
                "metadata": r.get("metadata", {})
            }
        for r in keyword_results:
            h = hashlib.md5(r['document'].encode()).hexdigest()
            kw = r['score'] * self.keyword_weight
            if h in merged:
                merged[h]["score"] += kw
                merged[h]["scores"]["keyword"] = r['score']
                merged[h]["methods"].append("keyword")
            else:
                merged[h] = {
                    "document": r['document'],
                    "score": kw,
                    "scores": {"vector": 0.0, "keyword": r['score']},
                    "methods": ["keyword"],
                    "metadata": r.get("metadata", {})
                }
        results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
        results = [r for r in results if r["score"] >= self.score_threshold]

        # rerank: simple cross-encoder-free rerank = boost dual-hit
        for r in results:
            if "vector" in r["methods"] and "keyword" in r["methods"]:
                r["score"] *= 1.15

        results.sort(key=lambda x: x["score"], reverse=True)
        return [{
            "document": r["document"],
            "score": round(r["score"],4),
            "method": "+".join(r["methods"]),
            "metadata": r.get("metadata",{}),
            "detail": r.get("scores",{})
        } for r in results[:self.top_k]]


def hybrid_query_multiple(kb_ids: List[str], query: str,
                          group: Optional[str] = None,
                          chapter: Optional[str] = None,
                          **searcher_kwargs) -> List[Dict]:
    """Cross-KB, but still scoped to group/chapter"""
    from services.knowledge_manager import kb_manager
    if not kb_ids: return []
    kbs = kb_manager.get_kbs_by_ids(kb_ids)
    if not kbs: return []
    searcher = HybridSearcher(**searcher_kwargs)
    all_results, seen = [], set()
    for kb in kbs:
        try:
            results = searcher.search(kb['collection_name'], query, group=group, chapter=chapter)
            for r in results:
                h = hashlib.md5(r['document'].encode()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    r['kb_id'] = kb['id']
                    r['kb_name'] = kb['name']
                    all_results.append(r)
        except Exception as e:
            print(f"Hybrid search KB {kb['name']} failed: {e}")
    all_results.sort(key=lambda x: x['score'], reverse=True)
    return all_results[:searcher.top_k]


class GroupedHybridSearcher:
    """Group-scoped: each group has independent kb_ids, weight, top_k, threshold"""
    def __init__(self, kb_groups: Dict[str, Dict]):
        self.groups = kb_groups

    def search(self, query: str, group_name: str = None,
               chapter: str = None) -> List[Dict]:
        if group_name:
            g = self.groups.get(group_name)
            if not g: return []
            res = hybrid_query_multiple(
                g.get("kb_ids", []), query,
                group=group_name, chapter=chapter,
                top_k=g.get("top_k", 2),
                score_threshold=g.get("threshold", 0.35),
                semantic_weight=g.get("semantic_weight", 0.6),
                keyword_weight=g.get("keyword_weight", 0.4),
            )
            for r in res: r["group"] = group_name
            return res

        # all groups
        out, seen = [], set()
        for name, cfg in self.groups.items():
            weight = cfg.get("weight", 1.0)
            res = hybrid_query_multiple(
                cfg.get("kb_ids", []), query,
                group=name, chapter=chapter,
                top_k=cfg.get("top_k", 2),
                score_threshold=cfg.get("threshold", 0.35),
                semantic_weight=cfg.get("semantic_weight", 0.6),
                keyword_weight=cfg.get("keyword_weight", 0.4),
            )
            for r in res:
                h = hashlib.md5(r.get('document','').encode()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    r["group"] = name
                    r["score"] *= weight
                    out.append(r)
        out.sort(key=lambda x: x["score"], reverse=True)
        return out[:5]
