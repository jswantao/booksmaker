# api/translate.py — 翻译端点（含术语表+后处理+Token优化+缓存）
import re
from fastapi import APIRouter
from models.schemas import TranslateRequest
from agents import AGENTS
from config import user_api_config
from core.dependencies import ConfigError
from embedding_providers import EmbeddingManager
from model_providers import LLMManager
from services.translation_memory import tm_instance
from services.knowledge_service import resolve_rag_kb_ids
from services.hybrid_search import hybrid_query_multiple
from services.translate_optimizer import (
    enhance_translation, truncate_tm_context, truncate_rag_context,
    cache_key, get_cached, set_cache
)

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
                return {"success": True, "translation": exact_match['target'],
                        "from_tm": True, "tm_match": "exact", "tm_count": exact_match['use_count'] + 1}

            try:
                q_emb = EmbeddingManager().embed([req.text], is_query=True)[0]
                tm_matches = tm_instance.search_by_embedding(q_emb, n_results=5, similarity_threshold=0.4)
            except Exception as e:
                print(f"TM vector search failed, fallback to Jaccard: {e}")
                tm_matches = tm_instance.search(req.text, threshold=0.4, limit=5)

        # K === Token 优化：缓存检查 ===
        ck = cache_key(req.text, len(tm_matches),
                       1 if (req.use_rag and req.kb_ids) else 0)
        cached = get_cached(ck)
        if cached:
            return {"success": True, "translation": cached,
                    "from_tm": False, "cached": True,
                    "tm_references": [
                        {"source": m['source'], "target": m['target'], "similarity": m['similarity']}
                        for m in tm_matches[:2]]}

        expert = AGENTS.get("世界史专家")
        sys_prompt = expert.system_prompt if expert else (
            "你是「世界史翻译官」，精通英语与中文，擅长翻译英文历史书籍为中文。"
            "要求：准确忠实、完整严谨、专有名词使用公认译名、学术风格、流畅自然。")
        messages = [{"role": "system", "content": sys_prompt}]

        # === Token 优化：TM 上下文截断（top-2, 每条≤300字） ===
        if tm_matches:
            tm_ctx = truncate_tm_context(tm_matches)
            if tm_ctx:
                messages.append({"role": "system", "content": f"翻译记忆参考（保持术语一致）：\n{tm_ctx}"})

        # === Token 优化：RAG 上下文截断（top-2, 每条≤400字） ===
        if req.use_rag:
            kb_ids = resolve_rag_kb_ids(req.kb_ids, req.group_id, "世界史专家")
            if kb_ids:
                items = hybrid_query_multiple(kb_ids, req.text, top_k=3, score_threshold=0.3,
                                              semantic_weight=0.7, keyword_weight=0.3)
                rag_ctx = truncate_rag_context(items)
                if rag_ctx:
                    messages.append({"role": "system", "content": f"参考知识库：\n{rag_ctx}"})

        if req.context:
            messages.append({"role": "system", "content": f"上下文：{req.context[:500]}"})

        messages.append({"role": "user", "content": f"请翻译以下英文历史文本为中文：\n\n{req.text}"})

        raw_translation = LLMManager().chat(messages, task="translate", temperature=0.3)

        # === 术语表 + 后处理增强 ===
        translation = enhance_translation(raw_translation)
        translation = re.sub(r'<[^>]+>', '', translation)

        # 缓存结果
        set_cache(ck, translation)

        # 存入 TM
        if req.use_tm:
            tm_instance.add(req.text, translation, context=req.context)
            try:
                emb = EmbeddingManager().embed([req.text], is_query=False)[0]
                tm_instance.add_embedding(req.text, translation, emb, context=req.context)
            except Exception as e:
                print(f"TM embedding store failed: {e}")

        return {"success": True, "translation": translation, "from_tm": False,
                "tm_references": [
                    {"source": m['source'], "target": m['target'], "similarity": m['similarity']}
                    for m in tm_matches[:2]]}
    except ConfigError as e:
        return {"success": False, "error": str(e), "code": "API_KEY_MISSING"}
    except Exception as e:
        return {"success": False, "error": str(e)}
