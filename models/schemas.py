# models/schemas.py
from typing import List, Optional
from pydantic import BaseModel

class ApiConfigRequest(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4-turbo-preview"
    embedding_model: str = "text-embedding-ada-002"
    embedding_provider: str = "openai"
    bge_model_id: str = "BAAI/bge-base-zh-v1.5"
    llm_provider: str = "openai"
    local_translate_model: str = "Qwen/Qwen2.5-1.5B-Instruct"
    local_epub_model: str = ""

class EmbeddingSwitchRequest(BaseModel):
    provider: str
    embedding_model: Optional[str] = None
    bge_model_id: Optional[str] = None

class TranslateRequest(BaseModel):
    text: str
    use_tm: bool = True
    use_rag: bool = False
    kb_ids: List[str] = []
    group_id: Optional[str] = None
    context: Optional[str] = None

class EpubRequest(BaseModel):
    content: str
    use_rag: bool = False
    kb_ids: List[str] = []
    group_id: Optional[str] = None
    user_epub_code: Optional[str] = None

class EpubReplaceRequest(BaseModel):
    translation: str
    epub_code: str

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
