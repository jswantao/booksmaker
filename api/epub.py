# api/epub.py — EPUB 替换端点（LLM 精确指令） + 文件下载
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from config import Config
from model_providers import LLMManager
from services.epub_service import build_epub_file

router = APIRouter()
config = Config()


class EpubReplaceRequest(BaseModel):
    translation: str       # 新译文
    epub_code: str         # 源 EPUB 代码（含 HTML 标签）
    title: str = ""        # EPUB 标题（可选）


def _build_replace_instruction(new_text: str, source_code: str) -> str:
    """构建精确替换指令——约束模型行为为"覆盖"而非"润色"。

    关键设计：
    - 用『新译文』/『EPUB代码』显式标记，消除歧义
    - "完整覆盖" 明确是替换操作，非润色/改写
    - "其他结构和标签保持不变" 约束模型不修改 HTML
    - 温度 0.1 确保确定性输出
    """
    return (
        f"请用以下『新译文』的内容，完整覆盖『EPUB代码』中的所有中文文本，"
        f"其他结构和标签保持不变。只输出替换后的完整代码。\n\n"
        f"## 新译文\n{new_text}\n\n"
        f"## EPUB代码\n{source_code}"
    )


@router.post("/api/epub/replace")
async def replace_epub(req: EpubReplaceRequest):
    """EPUB 替换：LLM 精确指令方式。

    使用精确指令格式约束模型：
    1. "完整覆盖" 语义 → 替换而非润色
    2. "结构和标签保持不变" → 标签/属性 100% 保留
    3. temperature=0.1 → 确定性输出
    """
    if len(req.translation) > 50000:
        return {"success": False, "error": "译文过长，最大50000字符", "code": "INPUT_TOO_LONG"}
    if len(req.epub_code) > 50000:
        return {"success": False, "error": "EPUB代码过长", "code": "INPUT_TOO_LONG"}

    try:
        instruction = _build_replace_instruction(req.translation, req.epub_code)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个精确的 EPUB 文本替换工具。你的唯一任务是：\n"
                    "1. 找到 EPUB 代码中所有中文文本节点\n"
                    "2. 用『新译文』完整覆盖这些文本\n"
                    "3. 保留所有 HTML 标签、属性、CSS 类名不变\n"
                    "4. 保留原文中的专有名词括注格式（如 romaioi、Attila）\n"
                    "5. 直接输出替换后的完整代码，不添加任何解释"
                )
            },
            {"role": "user", "content": instruction}
        ]

        result_code = LLMManager().chat(messages, task="epub", temperature=0.1)

        # 清理可能的代码块包装
        result_code = result_code.strip()
        if result_code.startswith("```"):
            lines = result_code.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            result_code = "\n".join(lines).strip()

        epub_path = build_epub_file(result_code,
                                     title=req.title or req.translation[:50])

        return {
            "success": True,
            "epub_code": result_code,
            "download_url": f"/api/download/epub/{epub_path.name}" if epub_path else None
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/api/download/epub/{filename}")
async def download_epub(filename: str):
    file_path = Path(config.UPLOAD_DIR) / "epub" / filename
    if not file_path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(file_path, media_type="application/epub+zip", filename=filename)
