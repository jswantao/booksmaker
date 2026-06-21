# models/schemas.py — Pydantic 请求/响应模型
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

ProviderChoice = Literal["openai", "local", "auto"]


class ApiConfigRequest(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"
    bge_model_id: str = "BAAI/bge-base-zh-v1.5"
    llm_provider: str = "openai"
    local_translate_model: str = "Qwen/Qwen2-7B-Instruct"
    local_epub_model: str = ""
    download_source: str = "huggingface"
    modelscope_cache_dir: str = ""


class TranslateRequest(BaseModel):
    text: str = Field(..., max_length=50000)
    source_lang: str = "en"
    target_lang: str = "zh"
    use_tm: bool = True
    use_rag: bool = False
    kb_ids: List[str] = []
    group_id: Optional[str] = None
    chapter: Optional[str] = None
    context: Optional[str] = None
    book_title: Optional[str] = Field(None, description="Memory bank key")
    provider: ProviderChoice = "auto"
    task: Literal["paragraph_translate", "long_text_translate"] = "paragraph_translate"


class EpubReplaceRequest(BaseModel):
    translation: str = Field(..., max_length=50000)
    epub_code: str = Field(..., max_length=100000)
    title: str = ""
    book_title: Optional[str] = None
    provider: ProviderChoice = "auto"


class KBBuildRequest(BaseModel):
    articles: List[str]
    target_kb_id: str
    group: Optional[str] = None
    chapter: Optional[str] = None
    provider: ProviderChoice = "auto"


class TermUpsertRequest(BaseModel):
    en_term: str
    zh_term: str
    kb_target: str = Field(default="global", description="用户指定术语库")


class CreateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None


class UpdateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None


class CreateKBRequest(BaseModel):
    name: str
    description: Optional[str] = None
    embedding_model: Optional[str] = None
    group_id: Optional[str] = None


class UpdateKBRequest(BaseModel):
    name: str
    description: Optional[str] = None
    group_id: Optional[str] = None
    embedding_model: Optional[str] = None


class AssignKBRequest(BaseModel):
    kb_ids: List[str]
    is_default: bool = False


class HybridSearchRequest(BaseModel):
    query: str
    kb_ids: Optional[List[str]] = None
    group_id: Optional[str] = None
    chapter: Optional[str] = None
    top_k: int = 3
    score_threshold: float = 0.35
    semantic_weight: float = 0.6
    keyword_weight: float = 0.4
