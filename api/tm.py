# api/tm.py — 翻译记忆库端点
from typing import List, Optional
from fastapi import APIRouter, Form, Request
from embedding_providers import EmbeddingManager
from config import user_api_config
from core.dependencies import get_client, get_model_config
from services.translation_memory import tm_instance

router = APIRouter()


@router.post("/api/tm/search")
@router.get("/api/tm/search")
async def search_tm(request: Request, q: Optional[str] = None, query: Optional[str] = Form(None), threshold: float = 0.5, limit: int = 5):
    try:
        query_text = q or query or ""
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                data = await request.json()
                query_text = data.get("query", query_text)
                threshold = data.get("threshold", threshold)
                limit = data.get("limit", limit)
            except Exception:
                pass
                
        if not query_text:
            return {"success": True, "results": []}
            
        exact = tm_instance.search_exact(query_text)
        if exact: return {"success": True, "results": [{**exact, "match_type": "exact"}]}
        results = tm_instance.search(query_text, threshold=threshold, limit=limit)
        for r in results: r['match_type'] = 'fuzzy'
        return {"success": True, "results": results}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/tm")
async def get_tm(limit: int = 100, offset: int = 0):
    try:
        return {"success": True, "results": tm_instance.get_all(limit=limit, offset=offset),
                "total": tm_instance.count()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/api/tm/clear")
async def clear_tm():
    try:
        tm_instance.clear()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/api/tm/{tm_id}")
async def delete_tm(tm_id: int):
    try:
        return {"success": tm_instance.delete(tm_id)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/tm")
@router.post("/api/tm/add")
async def add_tm(request: Request, source: Optional[str] = Form(None), target: Optional[str] = Form(None), context: Optional[str] = Form(None)):
    try:
        src, tgt, ctx = source, target, context
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                data = await request.json()
                src = data.get("source", src)
                tgt = data.get("target", tgt)
                ctx = data.get("context", ctx)
            except Exception:
                pass
                
        if not src or not tgt:
            return {"success": False, "error": "原文和译文不能为空"}
            
        ok = tm_instance.add(src, tgt, ctx)
        if ok:
            try:
                emb = EmbeddingManager().embed([src], is_query=False)[0]
                tm_instance.add_embedding(src, tgt, emb, context=ctx)
            except Exception as e:
                print(f"Manual TM embedding add failed: {e}")
        return {"success": ok}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/tm/reindex")
async def reindex_tm():
    if user_api_config.get("embedding_provider") != "bge" and not user_api_config.get("api_key"):
        return {"success": False, "error": "请先配置API密钥", "code": "API_KEY_MISSING"}
    try:
        def embedding_fn(texts: List[str]) -> List[List[float]]:
            return EmbeddingManager().embed(texts, is_query=False)

        return tm_instance.reindex_tm(embedding_fn)
    except Exception as e:
        return {"success": False, "error": str(e)}
