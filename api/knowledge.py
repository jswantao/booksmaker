# api/knowledge.py — 知识库管理、文档、分组、Agent-KB 端点
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from core.database import chroma_client
from config import user_api_config
from core.dependencies import ConfigError
from services.knowledge_manager import kb_manager
from services.knowledge_service import add_to_knowledge, query_knowledge
from models.schemas import (
    CreateKBRequest, UpdateKBRequest, CreateGroupRequest, UpdateGroupRequest, AssignKBRequest
)

router = APIRouter()


# ===== KB 分组 =====
@router.post("/api/kb/groups")
async def create_kb_group(req: CreateGroupRequest):
    try:
        return {"success": True, "group": kb_manager.create_group(req.name, req.description)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/kb/groups")
async def list_kb_groups():
    try:
        return {"success": True, "groups": kb_manager.get_all_groups()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.put("/api/kb/groups/{group_id}")
async def update_kb_group(group_id: str, req: UpdateGroupRequest):
    try:
        return {"success": kb_manager.update_group(group_id, req.name, req.description)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/api/kb/groups/{group_id}")
async def delete_kb_group(group_id: str):
    try:
        kb_manager.delete_group(group_id)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ===== KB CRUD =====
@router.post("/api/kb")
async def create_kb(req: CreateKBRequest):
    try:
        return {"success": True, "kb": kb_manager.create_kb(req.name, req.description, req.embedding_model,
                                                             req.group_id)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/kb")
async def list_kbs(group_id: Optional[str] = None):
    try:
        kbs = kb_manager.get_all_kbs(group_id=group_id)
        groups = kb_manager.get_all_groups()
        return {"success": True, "kbs": kbs, "groups": groups}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/kb/{kb_id}")
async def get_kb_detail(kb_id: str):
    try:
        kb = kb_manager.get_kb(kb_id)
        if not kb: raise HTTPException(404, "知识库不存在")
        try:
            col = chroma_client.get_collection(kb["collection_name"])
            results = col.get(limit=200)
            kb["documents"] = results.get("documents", [])
        except Exception:
            kb["documents"] = []
        return {"success": True, "kb": kb}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.put("/api/kb/{kb_id}")
async def update_kb(kb_id: str, req: UpdateKBRequest):
    try:
        return {"success": kb_manager.update_kb(kb_id, req.name, req.description, req.group_id,
                                                req.embedding_model)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/api/kb/{kb_id}")
async def delete_kb(kb_id: str):
    try:
        return {"success": kb_manager.delete_kb(kb_id)}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ===== KB 文档 =====
@router.post("/api/kb/{kb_id}/upload")
async def upload_to_kb(kb_id: str, file: UploadFile = File(...)):
    try:
        kb = kb_manager.get_kb(kb_id)
        if not kb: raise HTTPException(404, "知识库不存在")
        content = await file.read()
        text = content.decode('utf-8')
        chunks = [p.strip() for p in text.split('\n\n') if p.strip()]
        if not chunks: chunks = [text]
        add_to_knowledge(kb["collection_name"], chunks,
                         [{"source": file.filename, "kb_id": kb_id}] * len(chunks))
        kb_manager.update_document_count(kb_id)
        return {"success": True, "message": f"已添加 {len(chunks)} 个知识块",
                "kb": kb_manager.get_kb(kb_id)}
    except HTTPException:
        raise
    except ConfigError as e:
        return {"success": False, "error": str(e), "code": "API_KEY_MISSING"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/kb/{kb_id}/documents")
async def list_kb_documents(kb_id: str):
    try:
        kb = kb_manager.get_kb(kb_id)
        if not kb: raise HTTPException(404, "知识库不存在")
        try:
            col = chroma_client.get_collection(kb["collection_name"])
            results = col.get(limit=200)
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])
            return {"success": True, "documents": [
                {"content": docs[i], "metadata": metas[i] if i < len(metas) else {}} for i in range(len(docs))],
                    "count": len(docs)}
        except Exception:
            return {"success": True, "documents": [], "count": 0}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/api/kb/{kb_id}/documents")
async def clear_kb_documents(kb_id: str):
    try:
        kb = kb_manager.get_kb(kb_id)
        if not kb: raise HTTPException(404, "知识库不存在")
        try:
            chroma_client.delete_collection(kb["collection_name"])
            chroma_client.create_collection(kb["collection_name"])
        except Exception:
            pass
        kb_manager._execute("UPDATE knowledge_bases SET document_count=0 WHERE id=?", (kb_id,))
        return {"success": True, "message": "已清空知识库文档"}
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}


# ===== 旧版兼容: 知识库上传/查询 =====
@router.post("/api/upload_knowledge")
async def upload_knowledge(agent_name: str = Form(...), file: UploadFile = File(...)):
    if user_api_config.get("embedding_provider") != "bge" and not user_api_config.get("api_key"):
        return {"success": False, "error": "请先配置API密钥", "code": "API_KEY_MISSING"}
    try:
        content = await file.read()
        text = content.decode('utf-8')
        chunks = [p.strip() for p in text.split('\n\n') if p.strip()]
        if not chunks: chunks = [text]

        kb_ids = kb_manager.get_agent_default_kb_ids(agent_name)
        if not kb_ids:
            kb = kb_manager.create_kb(name=f"{agent_name}默认知识库", description=f"自动创建的{agent_name}知识库")
            kb_manager.assign_kb_to_agent(agent_name, kb["id"], is_default=True)
            kb_ids = [kb["id"]]

        for kb in kb_manager.get_kbs_by_ids(kb_ids):
            add_to_knowledge(kb["collection_name"], chunks,
                             [{"source": file.filename, "agent": agent_name, "kb_id": kb["id"]}] * len(chunks))
            kb_manager.update_document_count(kb["id"])
        return {"success": True, "message": f"已添加 {len(chunks)} 个知识块到 {len(kb_ids)} 个知识库"}
    except ConfigError as e:
        return {"success": False, "error": str(e), "code": "API_KEY_MISSING"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/knowledge/{agent_name}")
async def get_knowledge(agent_name: str):
    try:
        kb_ids = kb_manager.get_agent_default_kb_ids(agent_name)
        all_docs = []
        if kb_ids:
            for kb in kb_manager.get_kbs_by_ids(kb_ids):
                try:
                    col = chroma_client.get_collection(kb["collection_name"])
                    all_docs.extend(col.get(limit=100).get('documents', []))
                except Exception:
                    pass
        return {"success": True, "documents": all_docs}
    except Exception:
        return {"success": True, "documents": []}


# ===== Agent-KB 分配 =====
@router.get("/api/agents/{agent_name}/kbs")
async def get_agent_kbs(agent_name: str):
    try:
        return {"success": True, "assigned": kb_manager.get_agent_kbs(agent_name),
                "all_kbs": kb_manager.get_all_kbs()}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/agents/{agent_name}/kbs")
async def assign_kb_to_agent(agent_name: str, req: AssignKBRequest):
    try:
        for kb_id in req.kb_ids:
            kb_manager.assign_kb_to_agent(agent_name, kb_id, is_default=req.is_default)
        return {"success": True, "message": f"已为 {agent_name} 分配 {len(req.kb_ids)} 个知识库"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/api/agents/{agent_name}/kbs/{kb_id}")
async def unassign_kb_from_agent(agent_name: str, kb_id: str):
    try:
        kb_manager.unassign_kb_from_agent(agent_name, kb_id)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
