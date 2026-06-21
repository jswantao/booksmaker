# api/translate.py — 翻译端点（含术语表+后处理+Token优化+缓存+记忆库联动）
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
from services.memory_bank_manager import memory_bank_manager
from services.token_budget import TokenBudget, get_budget_for_provider

router = APIRouter()


@router.post("/api/translate")
async def translate(req: TranslateRequest):
    if user_api_config.get("llm_provider") != "local" and not user_api_config.get("api_key"):
        return {"success": False, "error": "请先配置API密钥", "code": "API_KEY_MISSING"}
    if len(req.text) > 50000:
        return {"success": False, "error": "文本过长，最大允许50000字符", "code": "INPUT_TOO_LONG"}

    try:
        # === 0. 加载记忆库（按书名隔离） ===
        # 有书名 → 专属记忆库（读写），无书名 → 只读种子术语（不写入）
        has_book = bool(req.book_name and req.book_name.strip())
        memory = memory_bank_manager.get_bank(req.book_name) if has_book else None
        # 活跃记忆库：优先专属，回退全局种子术语（只读）
        active_memory = memory if memory else memory_bank_manager.get_bank(None)

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

        # === Token 优化：缓存检查 ===
        mem_terms = len(active_memory.get_terminology())
        ck = cache_key(req.text, len(tm_matches),
                       1 if (req.use_rag and req.kb_ids) else 0,
                       mem_terms)
        cached = get_cached(ck)
        if cached:
            return {"success": True, "translation": cached,
                    "from_tm": False, "cached": True,
                    "tm_references": [
                        {"source": m['source'], "target": m['target'], "similarity": m['similarity']}
                        for m in tm_matches[:2]]}

        expert = AGENTS.get("世界史专家")
        if expert:
            terms = active_memory.get_terminology()
            if terms:
                terms_text = "\n".join(f"  {en} → {zh}" for en, zh in list(terms.items())[:15])
            else:
                terms_text = "（暂无术语公约）"
            sys_prompt = expert.system_prompt.replace("{dynamic_terms}", terms_text)
        else:
            sys_prompt = (
                "你是「世界史翻译官」，精通英语与中文，擅长翻译英文历史书籍为中文。"
                "要求：准确忠实、完整严谨、专有名词使用公认译名、学术风格、流畅自然。")
        messages = [{"role": "system", "content": sys_prompt}]

        # === 记忆库上下文 ===
        mem_ctx = active_memory.build_context_prompt(max_chars=800)
        if mem_ctx:
            label = "本书翻译记忆（严格遵循术语公约）" if has_book else "全局术语参考"
            messages.append({"role": "system", "content": f"{label}：\n{mem_ctx}"})

        # === TM 上下文（相关性过滤 + 截断） ===
        if tm_matches:
            useful_tm = [m for m in tm_matches if m.get('similarity', 0) > 0.7]
            if useful_tm:
                tm_ctx = truncate_tm_context(useful_tm)
                if tm_ctx:
                    messages.append({"role": "system", "content": f"翻译记忆参考：\n{tm_ctx}"})

        # === RAG 上下文 ===
        if req.use_rag:
            kb_ids = resolve_rag_kb_ids(req.kb_ids, req.group_id, "世界史专家")
            if kb_ids:
                items = hybrid_query_multiple(kb_ids, req.text, top_k=3, score_threshold=0.5,
                                              semantic_weight=0.7, keyword_weight=0.3)
                useful_rag = [r for r in items if r.get('score', 0) > 0.5]
                if useful_rag:
                    rag_ctx = truncate_rag_context(useful_rag)
                    if rag_ctx:
                        messages.append({"role": "system", "content": f"参考知识库：\n{rag_ctx}"})

        if req.context:
            messages.append({"role": "system", "content": f"上下文：{req.context[:500]}"})

        # 输出硬约束
        messages.append({"role": "system", "content": (
            "【输出格式硬约束】你只输出纯译文本身。禁止输出以下任何内容：\n"
            "- 禁止输出术语记录、词汇表、名词解释、术语附录\n"
            "- 禁止输出存疑清单、自检结果、翻译笔记\n"
            "- 禁止输出「请注意」「需要额外解释」「补充说明」等元评论\n"
            "- 禁止输出任何以「- \"术语\"：」开头的列表\n"
            "违反以上任何一条都会导致翻译结果被丢弃。"
        )})
        messages.append({"role": "user", "content": (
            f"翻译以下英文历史文本为中文：\n\n{req.text}"
        )})

        # === Token 预算（API 模式下自动截断超长上下文） ===
        llm_provider = user_api_config.get("llm_provider", "openai")
        if llm_provider != "local":
            budget = get_budget_for_provider(llm_provider, user_api_config.get("model_name", ""))
            messages = budget.fit(messages, preserve_first=1, preserve_last=1)

        raw_translation = LLMManager().chat(messages, task="translate", temperature=0.3)

        # === 后处理 ===
        glossary = active_memory.get_terminology()
        translation = enhance_translation(raw_translation, glossary=glossary)
        translation = re.sub(r'<[^>]+>', '', translation)

        # === 更新记忆库（仅当指定书名时写入） ===
        if has_book:
            try:
                memory.extract_terms_from_translation(translation, req.text)
                summary = translation[:200].replace('\n', ' ')
                chunk_id = -(len(memory.data.get("translated_chunks", [])) + 1)
                memory.queue_update('summary', {'chunk': chunk_id, 'summary': summary})
                memory.flush_pending()
            except Exception as e:
                print(f"[Translate] MemoryBank update failed: {e}")

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
                    for m in tm_matches[:2]],
                "memory_terms": len(memory.get_terminology())}
    except ConfigError as e:
        return {"success": False, "error": str(e), "code": "API_KEY_MISSING"}
    except Exception as e:
        return {"success": False, "error": str(e)}
