# api/terminology.py — Terminology Knowledge Base v3
# Maintain a shared terminology KB for frequently used terms.
# Users specify which KB to store terms into.

from fastapi import APIRouter
from models.schemas import TermUpsertRequest
from services.memory_bank_manager import memory_bank_manager
from services.knowledge_service import get_collection
from embedding_providers import EmbeddingManager
from typing import Dict

router = APIRouter()
TERM_COLLECTION_PREFIX = "term_kb_"

def _col(kb_target: str):
    name = f"{TERM_COLLECTION_PREFIX}{kb_target}"
    try:
        from core.database import chroma_client
        return get_collection(name)
    except Exception:
        from core.database import chroma_client
        return chroma_client.create_collection(name)

@router.get("/api/terminology")
async def list_terms(kb: str = "global", search: str = ""):
    # shared terminology KB
    # for simplicity, also read memory_bank global terminology
    global_bank = memory_bank_manager.get_bank(None)
    terms = global_bank.get_terminology()
    if search:
        q = search.lower()
        terms = {en:zh for en,zh in terms.items() if q in en.lower() or q in zh}
    return {"success": True, "kb": kb, "terms": terms, "count": len(terms)}

@router.post("/api/terminology")
async def add_term(req: TermUpsertRequest):
    """Users specify which KB to store terms into"""
    kb_target = req.kb_target.strip() or "global"
    
    # store in shared memory (global) — use writable bank dedicated for terminology
    global_bank = memory_bank_manager.get_writable_global_bank()
    global_bank.add_term(req.en_term.strip(), req.zh_term.strip())

    # ChromaDB terminology KB
    try:
        col = _col(kb_target)
        emb = EmbeddingManager().embed([req.en_term], is_query=False)[0]
        col.upsert(
            documents=[req.en_term],
            embeddings=[emb],
            metadatas=[{"zh_term": req.zh_term, "kb": kb_target}],
            ids=[f"term_{kb_target}_{req.en_term.lower().replace(' ','_')}"]
        )
    except Exception as e:
        print(f"term chroma write failed: {e}")
    return {"success": True, "kb": kb_target, "en": req.en_term, "zh": req.zh_term}

@router.get("/api/terminology/kbs")
async def list_kbs():
    # list available terminology KBs
    from core.database import chroma_client
    try:
        cols = chroma_client.list_collections()
        kbs = [c.name.replace(TERM_COLLECTION_PREFIX, "") for c in cols if c.name.startswith(TERM_COLLECTION_PREFIX)]
    except Exception:
        kbs = []
    if "global" not in kbs:
        kbs = ["global"] + kbs
    return {"kbs": kbs}

@router.delete("/api/terminology/{en_term}")
async def delete_term(en_term: str, kb: str = "global"):
    """Delete a term from the shared terminology bank."""
    en_term = en_term.strip()
    global_bank = memory_bank_manager.get_writable_global_bank()
    ok = global_bank.remove_term(en_term)
    # Also try to remove from ChromaDB term collection
    try:
        col = _col(kb)
        col.delete(ids=[f"term_{kb}_{en_term.lower().replace(' ','_')}"])
    except Exception:
        pass
    return {"success": ok, "en": en_term}
