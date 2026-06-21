# api/terminology.py — 术语知识库管理
"""全局术语知识库 CRUD，存储在 ChromaDB + 全局记忆库双写"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Dict
from services.memory_bank_manager import memory_bank_manager
from services.knowledge_service import get_collection
from embedding_providers import EmbeddingManager

router = APIRouter()
TERM_COLLECTION = "terminology_glossary"


class TermRequest(BaseModel):
    en_term: str
    zh_term: str


class TermDeleteRequest(BaseModel):
    en_term: str


def _ensure_collection():
    """确保术语 ChromaDB 集合存在"""
    try:
        return get_collection(TERM_COLLECTION)
    except Exception:
        from core.database import chroma_client
        return chroma_client.create_collection(TERM_COLLECTION)


@router.get("/api/terminology")
async def list_terms(search: str = ""):
    """列出全局术语（支持模糊搜索）"""
    global_bank = memory_bank_manager.get_bank(None)
    terms = global_bank.get_terminology()

    if search:
        q = search.lower()
        terms = {en: zh for en, zh in terms.items() if q in en.lower() or q in zh}

    return {"success": True, "terms": terms, "count": len(terms)}


@router.post("/api/terminology")
async def add_term(req: TermRequest):
    """添加/更新全局术语（双写：记忆库 + ChromaDB）"""
    if not req.en_term.strip() or not req.zh_term.strip():
        return {"success": False, "error": "术语和译名不能为空"}

    global_bank = memory_bank_manager.get_bank(None)
    global_bank.add_term(req.en_term.strip(), req.zh_term.strip())

    # 写入 ChromaDB 向量库（支持语义检索）
    try:
        col = _ensure_collection()
        emb = EmbeddingManager().embed([req.en_term], is_query=False)[0]
        col.upsert(
            documents=[req.en_term],
            embeddings=[emb],
            metadatas=[{"zh_term": req.zh_term, "source": "manual"}],
            ids=[f"term_{req.en_term.strip().lower().replace(' ', '_')}"]
        )
    except Exception as e:
        print(f"[Terminology] ChromaDB write failed (non-fatal): {e}")

    return {"success": True, "en_term": req.en_term, "zh_term": req.zh_term}


@router.delete("/api/terminology/{en_term:path}")
async def delete_term(en_term: str):
    """删除全局术语"""
    global_bank = memory_bank_manager.get_bank(None)
    ok = global_bank.remove_term(en_term)

    # 从 ChromaDB 删除
    try:
        col = _ensure_collection()
        col.delete(ids=[f"term_{en_term.strip().lower().replace(' ', '_')}"])
    except Exception as e:
        print(f"[Terminology] ChromaDB delete failed (non-fatal): {e}")

    return {"success": ok, "en_term": en_term}


@router.post("/api/terminology/batch")
async def batch_add_terms(terms: Dict[str, str]):
    """批量导入术语 {en_term: zh_term, ...}"""
    if not terms:
        return {"success": False, "error": "术语列表为空"}

    global_bank = memory_bank_manager.get_bank(None)
    added = 0
    for en, zh in terms.items():
        if en.strip() and zh.strip():
            global_bank.add_term(en.strip(), zh.strip())
            added += 1

    return {"success": True, "added": added}


@router.post("/api/terminology/search_semantic")
async def semantic_search(query: str, top_k: int = 5):
    """语义检索术语（用于翻译时自动匹配）"""
    try:
        col = _ensure_collection()
        if col.count() == 0:
            return {"success": True, "matches": []}

        q_emb = EmbeddingManager().embed([query], is_query=True)[0]
        results = col.query(query_embeddings=[q_emb], n_results=min(top_k, col.count()))

        matches = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                dist = results['distances'][0][i] if results.get('distances') else 0
                sim = 1.0 - min(dist, 1.0)
                meta = results['metadatas'][0][i] if results.get('metadatas') else {}
                matches.append({
                    "en_term": doc,
                    "zh_term": meta.get('zh_term', ''),
                    "similarity": round(sim, 4)
                })
        return {"success": True, "matches": matches}
    except Exception as e:
        return {"success": False, "error": str(e)}
