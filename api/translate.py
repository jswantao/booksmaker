# api/translate.py — Paragraph / Long-text Translation v3
import re
from fastapi import APIRouter
from models.schemas import TranslateRequest
from agents import get_agent
from config import user_api_config
from model_providers import LLMManager
from services.model_router import model_router
from services.translation_memory import tm_instance
from services.memory_bank_manager import memory_bank_manager
from services.hybrid_search import hybrid_query_multiple

router = APIRouter()

@router.post("/api/translate")
async def translate(req: TranslateRequest):
    # model selection: user independent choice local vs cloud
    task_name = req.task
    route = model_router.resolve_provider(task_name, None if req.provider=="auto" else req.provider)

    # Memory Base Rules
    book_title = (req.book_title or "").strip()
    has_book = bool(book_title)
    # Build dedicated memory bases per book, keyed by user-specified book title
    memory = memory_bank_manager.get_bank(book_title if has_book else None)
    # read_only automatically if no book_title

    # TM
    tm_refs = []
    if req.use_tm:
        exact = tm_instance.search_exact(req.text)
        if exact:
            return {"success": True, "translation": exact["target"], "from_tm": True}

        try:
            from embedding_providers import EmbeddingManager
            q_emb = EmbeddingManager().embed([req.text], is_query=True)[0]
            tm_refs = tm_instance.search_by_embedding(q_emb, n_results=2, similarity_threshold=0.7)
        except Exception:
            pass

    agent = get_agent("ParagraphTranslator" if task_name=="paragraph_translate" else "LongTextTranslator")
    terms = memory.get_terminology()
    terms_text = " | ".join(f"{en}→{zh}" for en, zh in list(terms.items())[:12]) if terms else "(无)"
    sys_prompt = agent.build_system_prompt(dynamic_terms=terms_text, context_summary="")

    messages = [{"role": "system", "content": sys_prompt}]

    # concise memory context
    mem_ctx = memory.build_context_prompt(max_chars=600)
    if mem_ctx:
        messages.append({"role": "system", "content": mem_ctx})

    # RAG: scoped to group/chapter only, not entire KB
    if req.use_rag and req.kb_ids:
        items = hybrid_query_multiple(
            req.kb_ids, req.text,
            group=req.group_id, chapter=req.chapter,
            top_k=2, score_threshold=0.35
        )
        if items:
            rag_snip = "\n".join(f"- {r['document'][:240]}" for r in items[:2])
            messages.append({"role": "system", "content": f"参考:\n{rag_snip}"})

    if tm_refs:
        tm_snip = "\n".join(f"{m['source'][:80]} → {m['target'][:80]}" for m in tm_refs[:1])
        messages.append({"role": "system", "content": f"TM:\n{tm_snip}"})

    messages.append({"role": "user", "content": req.text})

    # ensure provider configured
    llm = LLMManager()
    # configure on demand if missing
    if not llm.get_provider("translate"):
        if route["provider"] == "local":
            from model_providers import ModelLoadConfig, LLMConfig
            llm.configure_local(
                route["model"],
                task="translate",
                load_config=ModelLoadConfig(load_in_4bit=True if route.get("quant")=="4bit" else False,
                                            load_in_8bit=True if route.get("quant")=="8bit" else False),
                llm_config=LLMConfig(temperature=route["temperature"], max_tokens=route["max_tokens"])
            )
        else:
            # openai client must exist; assume configured elsewhere
            pass

    gen_kwargs = model_router.get_generation_kwargs(task_name)
    try:
        raw = llm.chat(messages, task="translate", **gen_kwargs)
    except Exception as e:
        # fallback: try default
        raw = llm.chat(messages, task="default", **gen_kwargs)

    translation = agent.process_response(raw)

    # Automatic Mechanism: Memory Base Auto-Construction
    if has_book:
        added = memory.auto_build_from_translation(req.text, translation)
    else:
        added = 0  # DO NOT store translations in memory base when no book title

    # TM store
    if req.use_tm:
        tm_instance.add(req.text, translation)

    return {
        "success": True,
        "translation": translation,
        "task": task_name,
        "provider": route["provider"],
        "model": route["model"],
        "memory_terms": len(terms),
        "memory_added": added,
        "book_title": book_title or None,
    }
