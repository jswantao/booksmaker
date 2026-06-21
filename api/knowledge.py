# api/knowledge.py — Knowledge Base Construction v3 (Dify hybrid)
from fastapi import APIRouter
from models.schemas import KBBuildRequest, HybridSearchRequest
from agents import get_agent
from model_providers import LLMManager
from services.model_router import model_router
from services.knowledge_service import add_to_knowledge
from services.hybrid_search import hybrid_query_multiple
import json

router = APIRouter()

@router.post("/api/kb/build")
async def build_kb(req: KBBuildRequest):
    """
    Knowledge Base Construction:
    Build structured knowledge base from externally provided articles
    Reference Dify's hybrid index model
    """
    agent = get_agent("KBBuilder")
    route = model_router.resolve_provider("kb_build", None if req.provider=="auto" else req.provider)
    gen_kwargs = model_router.get_generation_kwargs("kb_build")

    built = 0
    for article in req.articles:
        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": article[:4000]}
        ]
        try:
            llm = LLMManager()
            out = llm.chat(messages, task="kb_build", **gen_kwargs)
        except Exception:
            # fallback simple chunking
            out = json.dumps([{"text": article[i:i+400], "group": req.group or "default", "chapter": req.chapter or "", "keywords": []} for i in range(0, len(article), 400)])

        try:
            # clean possible fences
            if "```" in out:
                out = out.split("```")[1]
                if out.startswith("json"): out = out[4:]
            items = json.loads(out.strip())
            if not isinstance(items, list): items = [items]
        except Exception:
            items = [{"text": article[:500], "group": req.group or "default", "chapter": req.chapter or "", "keywords": []}]

        texts = []
        metas = []
        for it in items:
            t = (it.get("text") or "").strip()
            if not t: continue
            texts.append(t)
            metas.append({
                "group": it.get("group") or (req.group or "default"),
                "chapter": it.get("chapter") or (req.chapter or ""),
                "keywords": ",".join(it.get("keywords", []))[:200],
                "source": "kb_builder"
            })
        if texts:
            # Need collection name from kb_id – simplified: use kb_id directly
            from services.knowledge_manager import kb_manager
            kb = kb_manager.get_kb(req.target_kb_id)
            if kb:
                add_to_knowledge(kb["collection_name"], texts, metas)
                built += len(texts)

    return {"success": True, "chunks_built": built, "provider": route["provider"], "model": route["model"]}

@router.post("/api/kb/hybrid_search")
async def hybrid_search(req: HybridSearchRequest):
    """Dify-style hybrid: keyword + semantic + rerank, scoped to group/chapter"""
    results = hybrid_query_multiple(
        req.kb_ids or [],
        req.query,
        group=req.group_id,
        chapter=req.chapter,
        top_k=req.top_k,
        score_threshold=req.score_threshold,
        semantic_weight=req.semantic_weight,
        keyword_weight=req.keyword_weight
    )
    return {"success": True, "results": results, "count": len(results)}
