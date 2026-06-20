# api/translate.py — 翻译端点
from fastapi import APIRouter
from models.schemas import TranslateRequest
from models.agent import Agent
from config import user_api_config
from core.dependencies import get_model_config, ConfigError
from embedding_providers import EmbeddingManager
from model_providers import LLMManager
from services.translation_memory import tm_instance
from services.knowledge_service import resolve_rag_kb_ids, query_multiple_knowledge

router = APIRouter()


@router.post("/api/translate")
async def translate(req: TranslateRequest):
    if user_api_config.get("llm_provider") != "local" and not user_api_config.get("api_key"):
        return {"success": False, "error": "请先配置API密钥", "code": "API_KEY_MISSING"}
    if len(req.text) > 50000:
        return {"success": False, "error": "文本过长，最大允许50000字符", "code": "INPUT_TOO_LONG"}

    try:
        tm_matches = []
        if req.use_tm:
            exact_match = tm_instance.search_exact(req.text)
            if exact_match:
                tm_instance.add(req.text, exact_match['target'], context=req.context)
                return {"success": True, "translation": exact_match['target'], "from_tm": True,
                        "tm_match": "exact", "tm_count": exact_match['use_count'] + 1}

            try:
                q_emb = EmbeddingManager().embed([req.text], is_query=True)[0]
                tm_matches = tm_instance.search_by_embedding(q_emb, n_results=3, similarity_threshold=0.4)
            except Exception as e:
                print(f"TM vector search failed, fallback to Jaccard: {e}")
                tm_matches = tm_instance.search(req.text, threshold=0.4, limit=3)

        messages = [{"role": "system", "content": "你是「世界史翻译官」，精通英语与中文，擅长翻译英文历史书籍为中文。要求：准确忠实、完整严谨、专有名词使用公认译名、学术风格、流畅自然。"}]

        if tm_matches:
            tm_ctx = "\n".join(
                [f"参考翻译 {i + 1}:\n原文: {m['source']}\n译文: {m['target']}" for i, m in enumerate(tm_matches)])
            messages.append({"role": "system", "content": f"以下翻译记忆供参考保持一致性：\n{tm_ctx}"})

        if req.use_rag:
            kb_ids = resolve_rag_kb_ids(req.kb_ids, req.group_id, "世界史专家")
            if kb_ids:
                items = query_multiple_knowledge(kb_ids, req.text)
                if items:
                    ctx = "\n".join([f"[{i['kb_name']}] {i['document']}" for i in items])
                    messages.append({"role": "system", "content": f"参考知识库内容：\n{ctx}"})

        if req.context:
            messages.append({"role": "system", "content": f"上下文信息：{req.context}"})

        messages.append({"role": "user", "content": f"请翻译以下英文历史文本为中文：\n\n{req.text}"})

        translation = LLMManager().chat(messages, task="translate", temperature=0.3)

        if req.use_tm:
            tm_instance.add(req.text, translation, context=req.context)
            try:
                emb = EmbeddingManager().embed([req.text], is_query=False)[0]
                tm_instance.add_embedding(req.text, translation, emb, context=req.context)
            except Exception as e:
                print(f"TM embedding store failed: {e}")

        return {"success": True, "translation": translation, "from_tm": False,
                "tm_references": [
                    {"source": m['source'], "target": m['target'], "similarity": m['similarity']} for m in tm_matches]}
    except ConfigError as e:
        return {"success": False, "error": str(e), "code": "API_KEY_MISSING"}
    except Exception as e:
        return {"success": False, "error": str(e)}
