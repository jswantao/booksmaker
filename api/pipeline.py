# api/pipeline.py — Translation Pipeline API v3
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from services.translation_pipeline import TranslationPipeline

router = APIRouter()
_pipelines: dict = {}

class PipelineRunRequest(BaseModel):
    file_path: str
    book_title: str
    kb_ids: List[str] = []
    task: str = "long_text_translate"

@router.post("/api/pipeline/run")
async def pipeline_run(req: PipelineRunRequest):
    pipe = TranslationPipeline(book_title=req.book_title, kb_ids=req.kb_ids, task=req.task)
    _pipelines[req.book_title] = pipe
    output = pipe.run_long_text(req.file_path)
    return {"success": True, "output_chars": len(output), "book": req.book_title}

@router.get("/api/pipeline/status/{book_title}")
async def pipeline_status(book_title: str):
    pipe = _pipelines.get(book_title)
    if pipe:
        mem = pipe.memory
        return {"running": True, "terms": len(mem.get_terminology()), "book": book_title}
    return {"running": False}
