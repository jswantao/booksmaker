# api/pipeline.py — 翻译流水线 API
"""Pipeline API: 构建知识库 / 初始化记忆库 / 运行翻译 / 暂停恢复 / 状态查询 / 章节缝合"""

import os
import json
import threading
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List, Dict

from services.translation_pipeline import TranslationPipeline
from services.memory_bank import MemoryBank
from services.knowledge_manager import kb_manager
from services.document_processor import read_document
from config import user_api_config

router = APIRouter()

# 运行中的 pipeline 实例（支持暂停/恢复）
_active_pipelines: Dict[str, TranslationPipeline] = {}
_pipeline_threads: Dict[str, threading.Thread] = {}
_pipeline_results: Dict[str, str] = {}  # kb_name → final output


class BuildKBRequest(BaseModel):
    file_path: str
    kb_name: str
    chunk_size: int = 1200
    overlap: int = 150


class RunPipelineRequest(BaseModel):
    file_path: str
    kb_name: str
    memory_path: str = ""
    resume_from: int = 0
    auto_save_interval: int = 10


class MemoryInitRequest(BaseModel):
    memory_path: str
    project: str = ""
    terminology: Optional[dict] = None


class StitchRequest(BaseModel):
    memory_path: str


# ---- 文件上传 ----
@router.post("/api/pipeline/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文档文件（TXT/PDF），返回保存路径"""
    allowed_exts = {'.txt', '.md', '.text', '.pdf'}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_exts:
        return {"success": False, "error": f"不支持的文件类型: {ext}，仅支持 TXT/PDF"}

    upload_dir = Path("uploads/pipeline")
    upload_dir.mkdir(parents=True, exist_ok=True)
    save_path = upload_dir / file.filename

    content = await file.read()
    with open(save_path, 'wb') as f:
        f.write(content)

    # 尝试读取文本以验证
    try:
        text = read_document(str(save_path))
        chars = len(text)
    except Exception as e:
        return {"success": False, "error": f"文件读取失败: {e}"}

    return {"success": True, "file_path": str(save_path),
            "file_name": file.filename, "chars": chars}


# ---- 知识库构建 ----
@router.post("/api/pipeline/build-kb")
async def build_kb(req: BuildKBRequest):
    """离线构建知识库：读取文件 → 切分 → 嵌入 → 存入 ChromaDB"""
    if not Path(req.file_path).exists():
        return {"success": False, "error": f"文件不存在: {req.file_path}"}
    try:
        kb = _build_kb(req.file_path, req.kb_name, req.chunk_size, req.overlap)
        return {"success": True, "kb": kb}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _build_kb(file_path: str, kb_name: str, chunk_size: int, overlap: int):
    from services.document_processor import DocumentProcessor, read_document
    from services.knowledge_service import add_to_knowledge

    text = read_document(file_path)
    print(f"[API:Pipeline] Read {len(text)} chars from {file_path}")

    processor = DocumentProcessor(chunk_size=chunk_size, overlap=overlap)
    chapters = processor.split_chapters(text)

    existing = kb_manager.get_all_kbs()
    target = next((k for k in existing if k['name'] == kb_name), None)
    if not target:
        target = kb_manager.create_kb(name=kb_name,
                                      description=f"From {Path(file_path).name}",
                                      embedding_model="bge")

    total = 0
    for ch in chapters:
        chunks = processor.chunk_text(ch['content'])
        if not chunks:
            continue
        texts = [f"[{ch['title']}] {c['content']}" for c in chunks]
        meta = [{"source": Path(file_path).name, "chapter": ch['title'],
                 "chunk": str(c['index'])} for c in chunks]
        add_to_knowledge(target['collection_name'], texts, meta)
        total += len(chunks)

    kb_manager.update_document_count(target['id'])
    return {"name": target['name'], "collection_name": target['collection_name'],
            "chunks": total, "chapters": len(chapters)}


# ---- 记忆库管理 ----
@router.post("/api/pipeline/memory/init")
async def init_memory(req: MemoryInitRequest):
    """初始化或重置记忆库"""
    mem = MemoryBank(req.memory_path)
    if req.project:
        mem.data["project"] = req.project
    if req.terminology:
        mem.add_terms_batch(req.terminology)
    mem._save()
    return {"success": True, "memory": req.memory_path,
            "terminology_count": len(mem.get_terminology())}


@router.get("/api/pipeline/memory/{memory_path:path}")
async def get_memory(memory_path: str):
    """获取记忆库状态"""
    if not Path(memory_path).exists():
        return {"success": False, "error": "记忆库不存在"}
    mem = MemoryBank(memory_path)
    return {"success": True,
            "project": mem.data.get("project", ""),
            "progress": mem.data.get("progress", {}),
            "total_terms": len(mem.get_terminology()),
            "chunks_done": len(mem.data.get("translated_chunks", [])),
            "is_done": mem.is_done(),
            "completed_chapters": mem.data.get("completed_chapters", []),
            "core_arguments": len(mem.data.get("core_arguments", [])),
            "recent_summaries": len(mem.data.get("recent_summaries", []))}


# ---- 主流水线 ----
@router.post("/api/pipeline/run")
async def run_pipeline(req: RunPipelineRequest, background: BackgroundTasks):
    """启动翻译流水线（后台执行）"""
    if not Path(req.file_path).exists():
        return {"success": False, "error": f"文件不存在: {req.file_path}"}

    # Find KB collection
    existing = kb_manager.get_all_kbs()
    target = next((k for k in existing if k['name'] == req.kb_name), None)
    if not target:
        return {"success": False, "error":
                f"知识库不存在: {req.kb_name}，请先调用 /api/pipeline/build-kb"}

    memory_path = req.memory_path or f"memory/{Path(req.file_path).stem}_memory.json"
    pipeline = TranslationPipeline(req.kb_name, memory_path)
    _active_pipelines[req.kb_name] = pipeline

    def _run():
        try:
            result = pipeline.run(
                file_path=req.file_path,
                kb_collection=target['collection_name'],
                resume_from=req.resume_from,
                auto_save_interval=req.auto_save_interval
            )
            _pipeline_results[req.kb_name] = result
        except Exception as e:
            _pipeline_results[req.kb_name] = f"[错误] {e}"
            print(f"[Pipeline] Fatal error: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    _pipeline_threads[req.kb_name] = thread
    thread.start()

    return {"success": True, "message": "翻译流水线已启动",
            "kb_name": req.kb_name, "memory_path": memory_path}


@router.post("/api/pipeline/pause/{kb_name}")
async def pause_pipeline(kb_name: str):
    """暂停流水线"""
    pipe = _active_pipelines.get(kb_name)
    if pipe:
        pipe.pause()
        return {"success": True, "message": "已暂停"}
    return {"success": False, "error": "流水线未运行"}


@router.post("/api/pipeline/resume/{kb_name}")
async def resume_pipeline(kb_name: str):
    """恢复流水线"""
    pipe = _active_pipelines.get(kb_name)
    if pipe:
        pipe.resume()
        return {"success": True, "message": "已恢复"}
    return {"success": False, "error": "流水线未运行"}


@router.get("/api/pipeline/status/{kb_name}")
async def pipeline_status(kb_name: str):
    """查询流水线状态"""
    pipe = _active_pipelines.get(kb_name)
    if pipe:
        progress = pipe.get_progress()
        progress["running"] = True
        progress["has_result"] = kb_name in _pipeline_results
        return {"success": True, **progress}
    return {"success": True, "running": False,
            "message": "流水线未运行，可通过 /api/pipeline/memory/ 查询记忆库状态"}


@router.get("/api/pipeline/result/{kb_name}")
async def pipeline_result(kb_name: str):
    """获取流水线最终结果"""
    result = _pipeline_results.get(kb_name)
    if result:
        return {"success": True, "output": result}
    return {"success": False, "error": "翻译尚未完成或流水线未运行"}


# ---- 章节缝合 ----
@router.post("/api/pipeline/stitch")
async def stitch(req: StitchRequest):
    """对已翻译完成的记忆库执行章节缝合"""
    if not Path(req.memory_path).exists():
        return {"success": False, "error": "记忆库不存在"}

    mem = MemoryBank(req.memory_path)
    if not mem.is_done():
        return {"success": False,
                "error": "翻译尚未完成，请等待所有分段翻译完毕后执行缝合",
                "progress": mem.data.get("progress", {})}

    # 加载 partial_output 并执行缝合
    partial_path = Path(req.memory_path).parent / "partial_output.txt"
    if not partial_path.exists():
        return {"success": False, "error": "部分输出文件不存在，无法执行缝合"}

    # 从记忆库重建章节结构
    from services.translation_pipeline import TranslationPipeline
    pipeline = TranslationPipeline("stitch", req.memory_path)
    pipeline.memory = mem

    # 读取 partial_output 来重建 translations
    with open(partial_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 解析 chunk
    import re
    chunks_parsed = []
    translations_parsed = []
    pattern = r'--- Chunk (\d+) \[(.*?)\] ---\n(.*?)(?=\n--- Chunk|\Z)'
    for match in re.finditer(pattern, content, re.DOTALL):
        idx = int(match.group(1))
        chapter = match.group(2)
        trans = match.group(3).strip()
        # 确保列表足够长
        while len(chunks_parsed) <= idx:
            chunks_parsed.append({})
            translations_parsed.append("")
        chunks_parsed[idx] = {"chapter_title": chapter, "index": idx}
        translations_parsed[idx] = trans

    pipeline._chunks = chunks_parsed
    pipeline._translations = translations_parsed

    try:
        final_output = pipeline.stitch_chapters()
        return {"success": True, "output": final_output,
                "path": str(Path(req.memory_path).parent / "final_output.md")}
    except Exception as e:
        return {"success": False, "error": f"缝合失败: {e}"}


# ---- KB 列表（用于 Pipeline 选择） ----
@router.get("/api/pipeline/kbs")
async def list_pipeline_kbs():
    """获取可用于流水线的知识库列表"""
    kbs = kb_manager.get_all_kbs()
    return {"success": True, "kbs": [
        {"id": k['id'], "name": k['name'], "collection_name": k.get('collection_name', ''),
         "document_count": k.get('document_count', 0), "group_id": k.get('group_id', '')}
        for k in kbs
    ]}
