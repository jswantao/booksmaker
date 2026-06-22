# services/knowledge_service.py — RAG 知识库操作
# 模块职责：ChromaDB 集合管理、嵌入存储、多 KB 检索、迁移

import hashlib
import threading
from typing import List, Dict, Optional
from core.database import chroma_client, _chroma_migration_lock
from embedding_providers import EmbeddingManager
from config import user_api_config
from core.dependencies import ConfigError


def get_collection(name: str):
    """获取或创建 ChromaDB 集合，处理版本迁移"""
    try:
        return chroma_client.get_collection(name)
    except KeyError as e:
        if '_type' in str(e):
            with _chroma_migration_lock:
                try:
                    return chroma_client.get_collection(name)
                except KeyError:
                    print("[ChromaDB] Version migration detected, resetting database...")
                    chroma_client.reset()
                    return chroma_client.create_collection(name)
        return chroma_client.create_collection(name)
    except Exception:
        try:
            return chroma_client.create_collection(name)
        except KeyError as e:
            if '_type' in str(e):
                with _chroma_migration_lock:
                    print("[ChromaDB] Version migration detected, resetting database...")
                    chroma_client.reset()
                    return chroma_client.create_collection(name)
            raise


def add_to_knowledge(collection_name: str, texts: List[str], metadatas: List[Dict] = None):
    if user_api_config.get("embedding_provider") != "bge" and not user_api_config.get("api_key"):
        raise ConfigError("请先配置API密钥")

    collection = get_collection(collection_name)
    ids = [hashlib.md5(t.encode()).hexdigest()[:12] for t in texts]
    embeddings = EmbeddingManager().embed(texts, is_query=False)

    if metadatas is None:
        metadatas = [{"source": "user_upload"} for _ in texts]

    collection.add(documents=texts, embeddings=embeddings, metadatas=metadatas, ids=ids)
    return ids


def query_knowledge(collection_name: str, query: str, n_results: int = 3) -> List[str]:
    if user_api_config.get("embedding_provider") != "bge" and not user_api_config.get("api_key"):
        return []

    try:
        collection = chroma_client.get_collection(collection_name)
    except Exception:
        return []

    try:
        query_embedding = EmbeddingManager().embed([query], is_query=True)[0]
        results = collection.query(query_embeddings=[query_embedding], n_results=n_results)
        return results['documents'][0] if results['documents'] else []
    except Exception as e:
        print(f"Knowledge query failed [{collection_name}]: {e}")
        return []


def resolve_rag_kb_ids(req_kb_ids: Optional[List[str]], req_group_id: Optional[str], agent_name: str) -> List[str]:
    from services.knowledge_manager import kb_manager
    if req_kb_ids: return req_kb_ids
    if req_group_id:
        kbs = kb_manager.get_kbs_by_group(req_group_id)
        return [kb["id"] for kb in kbs]
    return kb_manager.get_agent_default_kb_ids(agent_name)


def migrate_legacy_knowledge():
    """Migrate legacy ChromaDB collections to KB manager, assigning to both
    legacy agent names (frontend compat) and current agent names (agents.py)."""
    from services.knowledge_manager import kb_manager
    # Each legacy collection maps to a primary legacy name + current agent names
    legacy_map = {
        "history_knowledge": {
            "primary": "世界史专家",
            "aliases": ["ParagraphTranslator", "LongTextTranslator"],
        },
        "epub_knowledge": {
            "primary": "EPUB编辑",
            "aliases": ["EpubReplacer"],
        },
    }
    for collection_name, mapping in legacy_map.items():
        try:
            col = chroma_client.get_collection(collection_name)
            doc_count = col.count()
        except Exception:
            continue
        if doc_count == 0:
            continue
        existing = kb_manager._execute_one(
            "SELECT id FROM knowledge_bases WHERE collection_name = ?", (collection_name,))
        if existing:
            for name in [mapping["primary"]] + mapping["aliases"]:
                kb_manager.assign_kb_to_agent(name, existing[0], is_default=(name == mapping["primary"]))
            continue
        kb = kb_manager.create_kb(
            name=f"{mapping['primary']}默认知识库",
            description=f"从旧版 {collection_name} 自动迁移",
            collection_name=collection_name)
        for name in [mapping["primary"]] + mapping["aliases"]:
            kb_manager.assign_kb_to_agent(name, kb["id"], is_default=(name == mapping["primary"]))
        kb_manager.update_document_count(kb["id"])
        print(f"[Migration] Created KB '{kb['name']}' from '{collection_name}' ({doc_count} docs)")


# ---------------------------------------------------------------------------
# LangChain integration: VectorStore wrappers
# ---------------------------------------------------------------------------
def get_langchain_vectorstore(collection_name: str):
    """Return a langchain-chroma Chroma VectorStore wrapping the named collection.

    Uses QoderWorkEmbeddings (our LangChain Embeddings adapter) so that
    LCEL chains and retrievers can query our ChromaDB collections directly.
    Returns None if the collection does not exist or is empty.
    """
    try:
        from langchain_chroma import Chroma
        from langchain_adapters.embeddings import QoderWorkEmbeddings

        col = chroma_client.get_collection(collection_name)
        if col.count() == 0:
            return None

        return Chroma(
            collection_name=collection_name,
            embedding_function=QoderWorkEmbeddings(),
        )
    except Exception as e:
        print(f"[LCEL] VectorStore for '{collection_name}' failed: {e}")
        return None


def add_documents_lcel(collection_name: str, texts: List[str],
                       metadatas: Optional[List[Dict]] = None) -> List[str]:
    """Add documents via langchain-chroma Chroma.add_texts() with pre-computed embeddings.

    This is an alternative to add_to_knowledge() that goes through the LangChain
    VectorStore API. Both paths produce identical results in ChromaDB.
    """
    if user_api_config.get("embedding_provider") != "bge" and not user_api_config.get("api_key"):
        raise ConfigError("请先配置API密钥")

    vectorstore = get_langchain_vectorstore(collection_name)
    if vectorstore is None:
        # Collection doesn't exist yet — create via raw ChromaDB first
        get_collection(collection_name)
        vectorstore = get_langchain_vectorstore(collection_name)

    ids = [hashlib.md5(t.encode()).hexdigest()[:12] for t in texts]
    embeddings = EmbeddingManager().embed(texts, is_query=False)

    if metadatas is None:
        metadatas = [{"source": "user_upload"} for _ in texts]

    vectorstore.add_texts(
        texts=texts,
        metadatas=metadatas,
        ids=ids,
        embeddings=embeddings,
    )
    return ids
