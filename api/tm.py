# api/tm.py — 翻译记忆库端点
from typing import List
from fastapi import APIRouter, Form
from embedding_providers import EmbeddingManager
from config import user_api_config
from core.dependencies import get_client, get_model_config
from services.translation_memory import tm_instance

router = APIRouter()


@router.post("/api/tm/search")
async def search_tm(query: str = Form(...), threshold: float = Form(0.5), limit: int = Form(5)):
    try:
        exact = tm_instance.search_exact(query)
        if exact: return {"success": True, "results": [{**exact, "match_type": "exact"}]}
        results = tm_instance.search(query, threshold=threshold, limit=limit)
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


@router.post("/api/tm/add")
async def add_tm(source: str = Form(...), target: str = Form(...), context: str = Form(None)):
    try:
        ok = tm_instance.add(source, target, context)
        if ok:
            try:
                client = get_client()
                mc = get_model_config()
                resp = client.embeddings.create(model=mc["embedding_model"], input=[source])
                tm_instance.add_embedding(source, target, resp.data[0].embedding, context=context)
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
