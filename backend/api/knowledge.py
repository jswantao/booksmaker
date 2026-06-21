# api/knowledge.py — Knowledge Base CRUD + Construction + Search v3
from fastapi import APIRouter, UploadFile, File, Form
from models.schemas import (
    KBBuildRequest, HybridSearchRequest,
    CreateKBRequest, UpdateKBRequest,
    CreateGroupRequest, UpdateGroupRequest,
)
from agents import get_agent_by_task
from model_providers import LLMManager
from services.model_router import model_router
from services.knowledge_service import add_to_knowledge
from services.hybrid_search import hybrid_query_multiple
from services.knowledge_manager import kb_manager
import json
import os

router = APIRouter()

# ==================== KB CRUD ====================

@router.get("/api/kb")
async def list_kbs():
    """List all knowledge bases and groups."""
    try:
        kbs = kb_manager.get_all_kbs()
        groups = kb_manager.get_all_groups()
        return {"success": True, "kbs": kbs, "groups": groups}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/kb")
async def create_kb(req: CreateKBRequest):
    """Create a new knowledge base."""
    try:
        kb = kb_manager.create_kb(
            name=req.name,
            description=req.description or "",
            embedding_model=req.embedding_model or "",
            group_id=req.group_id,
        )
        return {"success": True, "kb": kb}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.put("/api/kb/{kb_id}")
async def update_kb(kb_id: str, req: UpdateKBRequest):
    """Update a knowledge base."""
    try:
        ok = kb_manager.update_kb(
            kb_id,
            name=req.name if req.name else None,
            description=req.description,
            group_id=req.group_id,
            embedding_model=req.embedding_model,
        )
        if not ok:
            return {"success": False, "error": "KB not found or no fields to update"}
        return {"success": True, "kb": kb_manager.get_kb(kb_id)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/api/kb/{kb_id}")
async def delete_kb(kb_id: str):
    """Delete a knowledge base and its ChromaDB collection."""
    try:
        ok = kb_manager.delete_kb(kb_id)
        if not ok:
            return {"success": False, "error": "KB not found"}
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/kb/{kb_id}/upload")
async def upload_to_kb(kb_id: str, file: UploadFile = File(...)):
    """Upload a .txt/.md file into a knowledge base."""
    kb = kb_manager.get_kb(kb_id)
    if not kb:
        return {"success": False, "error": "KB not found"}
    try:
        content = (await file.read()).decode("utf-8", errors="ignore")
    except Exception as e:
        return {"success": False, "error": f"Failed to read file: {e}"}

    # Simple chunking: split by double newline or fixed size
    chunks = [c.strip() for c in content.split("\n\n") if c.strip()]
    if not chunks:
        chunks = [content[i:i+800].strip() for i in range(0, len(content), 800)]
    chunks = [c for c in chunks if len(c) > 20]

    if not chunks:
        return {"success": False, "error": "No usable text found in file"}

    metadatas = [{"source": file.filename, "group": kb.get("group_id", ""), "chunk_index": str(i)}
                 for i in range(len(chunks))]
    try:
        ids = add_to_knowledge(kb["collection_name"], chunks, metadatas)
        kb_manager.update_document_count(kb_id)
        return {"success": True, "message": f"上传成功，{len(ids)} 条片段已入库"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== Group CRUD ====================

@router.get("/api/kb/groups")
async def list_groups():
    """List all KB groups."""
    try:
        groups = kb_manager.get_all_groups()
        return {"success": True, "groups": groups}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/kb/groups")
async def create_group(req: CreateGroupRequest):
    """Create a new KB group."""
    try:
        group = kb_manager.create_group(name=req.name, description=req.description or "")
        return {"success": True, "group": group}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.put("/api/kb/groups/{group_id}")
async def update_group(group_id: str, req: UpdateGroupRequest):
    """Update a KB group."""
    try:
        ok = kb_manager.update_group(group_id, name=req.name if req.name else None,
                                     description=req.description)
        if not ok:
            return {"success": False, "error": "Group not found"}
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/api/kb/groups/{group_id}")
async def delete_group(group_id: str):
    """Delete a KB group (unlinks its KBs)."""
    try:
        kb_manager.delete_group(group_id)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== Knowledge Upload (legacy) ====================

@router.get("/api/knowledge")
async def knowledge_status():
    """Get knowledge base summary status."""
    try:
        kbs = kb_manager.get_all_kbs()
        groups = kb_manager.get_all_groups()
        total_docs = sum(kb.get("document_count", 0) for kb in kbs)
        return {"success": True, "kb_count": len(kbs), "group_count": len(groups),
                "total_documents": total_docs}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/knowledge/upload")
async def upload_knowledge_legacy(
    file: UploadFile = File(...),
    agent_name: str = Form(""),
    kb_id: str = Form(""),
):
    """Legacy knowledge upload — associates file with an agent or KB."""
    try:
        content = (await file.read()).decode("utf-8", errors="ignore")
    except Exception as e:
        return {"success": False, "error": f"Failed to read file: {e}"}

    chunks = [c.strip() for c in content.split("\n\n") if len(c.strip()) > 20]
    if not chunks:
        chunks = [content[i:i+800].strip() for i in range(0, len(content), 800) if len(content[i:i+800].strip()) > 20]

    if not chunks:
        return {"success": False, "error": "No usable text found"}

    # Resolve target KB: explicit kb_id > agent default > create new
    target_kb = None
    if kb_id:
        target_kb = kb_manager.get_kb(kb_id)

    if not target_kb and agent_name:
        default_ids = kb_manager.get_agent_default_kb_ids(agent_name)
        if default_ids:
            target_kb = kb_manager.get_kb(default_ids[0])

    if not target_kb:
        # Auto-create a KB for this agent
        kb_name = f"{agent_name}知识库" if agent_name else "默认知识库"
        target_kb = kb_manager.create_kb(name=kb_name, description="自动创建")

    metadatas = [{"source": file.filename, "agent": agent_name, "chunk_index": str(i)}
                 for i in range(len(chunks))]
    try:
        ids = add_to_knowledge(target_kb["collection_name"], chunks, metadatas)
        kb_manager.update_document_count(target_kb["id"])
        return {"success": True, "message": f"上传成功，{len(ids)} 条片段已入库",
                "kb_id": target_kb["id"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== KB Build (LLM-assisted) ====================

@router.post("/api/kb/build")
async def build_kb(req: KBBuildRequest):
    """
    Knowledge Base Construction:
    Build structured knowledge base from externally provided articles
    Reference Dify's hybrid index model
    """
    agent = get_agent_by_task("kb_build")
    if agent is None:
        return {"success": False, "error": "KBBuilder Agent未找到"}
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
            from services.knowledge_manager import kb_manager
            kb = kb_manager.get_kb(req.target_kb_id)
            if kb:
                add_to_knowledge(kb["collection_name"], texts, metas)
                built += len(texts)

    return {"success": True, "chunks_built": built, "provider": route["provider"], "model": route["model"]}


# ==================== Hybrid Search ====================

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
