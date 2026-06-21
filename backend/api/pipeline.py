# api/pipeline.py — Translation Pipeline API v3
from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import os

from services.translation_pipeline import TranslationPipeline
from services.memory_bank_manager import memory_bank_manager
from services.knowledge_manager import kb_manager
from services.knowledge_service import add_to_knowledge
from services.memory_bank import MemoryBank

router = APIRouter()
_pipelines: dict = {}

UPLOAD_DIR = Path("./uploads")

# ---- Request Models ----

class PipelineRunRequest(BaseModel):
    file_path: str
    book_title: str = ""
    kb_ids: List[str] = []
    memory_path: str = ""
    resume_from: int = 0
    auto_save_interval: int = 10
    task: str = "long_text_translate"

class PipelineBuildKbRequest(BaseModel):
    file_path: str
    kb_name: str
    chunk_size: int = 1200
    overlap: int = 150

class MemoryInitRequest(BaseModel):
    memory_path: str
    project: str = ""
    terminology: Optional[dict] = None

class StitchRequest(BaseModel):
    memory_path: str


# ---- Pipeline Run ----

@router.post("/api/pipeline/run")
async def pipeline_run(req: PipelineRunRequest):
    book_title = req.book_title or Path(req.file_path).stem
    pipe = TranslationPipeline(book_title=book_title, kb_ids=req.kb_ids, task=req.task)
    _pipelines[book_title] = pipe
    output = pipe.run_long_text(req.file_path)
    return {"success": True, "output_chars": len(output), "book": book_title}


# ---- Pipeline Upload ----

@router.post("/api/pipeline/upload")
async def pipeline_upload(file: UploadFile = File(...)):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / file.filename
    content = await file.read()
    file_path.write_bytes(content)
    return {"success": True, "file_path": str(file_path), "filename": file.filename}


# ---- Pipeline Build KB ----

@router.post("/api/pipeline/build-kb")
async def pipeline_build_kb(req: PipelineBuildKbRequest):
    text = Path(req.file_path).read_text(encoding="utf-8", errors="ignore")
    # Simple chunking
    chunks = []
    i = 0
    while i < len(text):
        chunk = text[i:i + req.chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        i += req.chunk_size - req.overlap

    if not chunks:
        return {"success": False, "error": "No text chunks generated"}

    # Create or reuse KB
    existing = [kb for kb in kb_manager.get_all_kbs() if kb["name"] == req.kb_name]
    if existing:
        kb = existing[0]
    else:
        kb = kb_manager.create_kb(name=req.kb_name, description=f"From {req.file_path}")

    metadatas = [{"source": req.file_path, "chunk_index": str(i)} for i in range(len(chunks))]
    ids = add_to_knowledge(kb["collection_name"], chunks, metadatas)
    kb_manager.update_document_count(kb["id"])
    return {"success": True, "kb_id": kb["id"], "chunks": len(ids)}


# ---- Pipeline Control ----

@router.post("/api/pipeline/pause/{kb_name}")
async def pipeline_pause(kb_name: str):
    pipe = _pipelines.get(kb_name)
    if pipe:
        pipe.pause()
        return {"success": True, "paused": True}
    return {"success": False, "error": "Pipeline not found"}


@router.post("/api/pipeline/resume/{kb_name}")
async def pipeline_resume(kb_name: str):
    pipe = _pipelines.get(kb_name)
    if pipe:
        pipe.resume()
        return {"success": True, "paused": False}
    return {"success": False, "error": "Pipeline not found"}


@router.get("/api/pipeline/status/{kb_name}")
async def pipeline_status(kb_name: str):
    pipe = _pipelines.get(kb_name)
    if pipe:
        mem = pipe.memory
        return {"success": True, "running": True, "paused": pipe._paused,
                "terms": len(mem.get_terminology()), "book": kb_name}
    return {"success": True, "running": False}


@router.get("/api/pipeline/result/{kb_name}")
async def pipeline_result(kb_name: str):
    pipe = _pipelines.get(kb_name)
    if pipe:
        out_dir = Path(memory_bank_manager._get_bank_path(pipe.book_title)).parent
        final = out_dir / "final_output.md"
        if final.exists():
            return {"success": True, "output": final.read_text(encoding="utf-8")}
        return {"success": True, "output": "", "message": "No final output yet"}
    return {"success": False, "error": "Pipeline not found"}


# ---- Pipeline Memory ----

@router.get("/api/pipeline/memory/{path:path}")
async def pipeline_get_memory(path: str):
    try:
        bank = MemoryBank(path, book_title="", read_only=True)
        return {"success": True, "terms": bank.get_terminology(),
                "summaries": bank.data.get("summaries", []),
                "progress": bank.data.get("progress", {})}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/pipeline/memory/init")
async def pipeline_init_memory(req: MemoryInitRequest):
    bank = memory_bank_manager.get_bank(req.project or None)
    if req.terminology:
        bank.add_terms_batch(req.terminology)
    return {"success": True, "path": bank.file_path}


# ---- Pipeline Stitch ----

@router.post("/api/pipeline/stitch")
async def pipeline_stitch(req: StitchRequest):
    try:
        bank = MemoryBank(req.memory_path, book_title="", read_only=True)
        terms = bank.get_terminology()
        summaries = bank.data.get("summaries", [])
        # Build a simple stitched output from memory
        lines = ["# 翻译终稿", "", f"## 术语表 ({len(terms)} 条)", ""]
        for en, zh in list(terms.items())[:50]:
            lines.append(f"- **{en}** → {zh}")
        lines.append("")
        lines.append(f"## 摘要 ({len(summaries)} 条)")
        for s in summaries:
            if isinstance(s, dict):
                lines.append(f"- [{s.get('chunk', '?')}] {s.get('text', '')}")
            else:
                lines.append(f"- {s}")
        final_text = "\n".join(lines)
        return {"success": True, "final_output": final_text}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---- Pipeline KBs ----

@router.get("/api/pipeline/kbs")
async def pipeline_list_kbs():
    try:
        kbs = kb_manager.get_all_kbs()
        return {"success": True, "kbs": kbs}
    except Exception as e:
        return {"success": False, "error": str(e)}
