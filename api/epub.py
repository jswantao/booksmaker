# api/epub.py — EPUB 生成/替换/下载端点
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from models.schemas import EpubRequest, EpubReplaceRequest
from agents import AGENTS
from config import user_api_config, Config
from core.dependencies import ConfigError
from model_providers import LLMManager
from services.knowledge_service import resolve_rag_kb_ids, query_multiple_knowledge
from services.epub_service import build_epub_file

router = APIRouter()
config = Config()


@router.post("/api/generate_epub")
async def generate_epub(req: EpubRequest):
    if user_api_config.get("llm_provider") != "local" and not user_api_config.get("api_key"):
        return {"success": False, "error": "请先配置API密钥", "code": "API_KEY_MISSING"}
    if len(req.content) > 100000:
        return {"success": False, "error": "内容过长，最大允许100000字符", "code": "INPUT_TOO_LONG"}
    try:
        expert = AGENTS.get("EPUB编辑")
        sys_prompt = expert.system_prompt if expert else "你是EPUB电子书编辑专家，精通EPUB格式和XHTML/CSS。根据用户提供的中文内容生成EPUB代码。"
        messages = [{"role": "system", "content": sys_prompt}]
        if req.use_rag:
            kb_ids = resolve_rag_kb_ids(req.kb_ids, req.group_id, "EPUB编辑")
            if kb_ids:
                items = query_multiple_knowledge(kb_ids, req.content)
                if items:
                    ctx = "\n".join([f"[{i['kb_name']}] {i['document']}" for i in items])
                    messages.append({"role": "system", "content": f"参考知识库示例：\n{ctx}"})
        if req.user_epub_code:
            prompt = f"将以下译文替换到EPUB代码中，返回完整EPUB代码。\n译文：{req.content}\nEPUB代码：{req.user_epub_code}"
        else:
            prompt = f"根据以下中文内容生成完整EPUB代码（OPF+NCX+XHTML+CSS）：\n{req.content}"
        messages.append({"role": "user", "content": prompt})
        epub_code = LLMManager().chat(messages, task="epub", temperature=0.4)
        epub_path = build_epub_file(epub_code, title=req.content[:50] if req.content else "Generated")
        return {"success": True, "epub_code": epub_code,
                "download_url": f"/api/download/epub/{epub_path.name}" if epub_path else None}
    except ConfigError as e:
        return {"success": False, "error": str(e), "code": "API_KEY_MISSING"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/replace_epub")
async def replace_epub(req: EpubReplaceRequest):
    if user_api_config.get("llm_provider") != "local" and not user_api_config.get("api_key"):
        return {"success": False, "error": "请先配置API密钥", "code": "API_KEY_MISSING"}
    if len(req.translation) > 100000 or len(req.epub_code) > 100000:
        return {"success": False, "error": "内容过长", "code": "INPUT_TOO_LONG"}
    try:
        expert = AGENTS.get("EPUB编辑")
        sys_prompt = expert.system_prompt if expert else "你是EPUB编辑专家，擅长精确替换EPUB内容而不改变结构和样式。"
        messages = [{"role": "system", "content": sys_prompt}]
        
        if req.use_rag:
            kb_ids = resolve_rag_kb_ids(req.kb_ids, req.group_id, "EPUB编辑")
            if kb_ids:
                items = query_multiple_knowledge(kb_ids, req.translation)
                if items:
                    ctx = "\n".join([f"[{i['kb_name']}] {i['document']}" for i in items])
                    messages.append({"role": "system", "content": f"参考知识库规范与示例：\n{ctx}"})
                    
        prompt = f"将以下新译文精确替换到EPUB代码中，保持所有HTML标签（如 <p>, <span> 等）、CSS类名（class属性）、属性（如 id, href 等）完全不变，只替换标签之间的文本节点。\n新译文：{req.translation}\nEPUB代码：{req.epub_code}\n请只返回替换后的完整EPUB代码。"
        messages.append({"role": "user", "content": prompt})
        
        epub_code = LLMManager().chat(messages, task="epub", temperature=0.1)
        epub_path = build_epub_file(epub_code, title="Replaced_EPUB")
        return {"success": True, "epub_code": epub_code,
                "download_url": f"/api/download/epub/{epub_path.name}" if epub_path else None}
    except ConfigError as e:
        return {"success": False, "error": str(e), "code": "API_KEY_MISSING"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/download/epub/{filename}")
async def download_epub(filename: str):
    file_path = Path(config.UPLOAD_DIR) / "epub" / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file_path, media_type="application/epub+zip", filename=filename)
