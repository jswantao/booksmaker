# services/embedding_service.py — 嵌入提供者同步
# 模块职责：根据配置同步 EmbeddingManager 状态

from embedding_providers import EmbeddingManager, BGEEmbeddingProvider
from config import user_api_config
from core.dependencies import get_client


def sync_embedding_manager():
    """根据当前 user_api_config 同步 EmbeddingManager"""
    manager = EmbeddingManager()
    provider_type = user_api_config.get("embedding_provider", "openai")

    if provider_type == "bge":
        model_id = user_api_config.get("bge_model_id", "BAAI/bge-base-zh-v1.5")
        manager.configure_bge(model_id=model_id)
        print(f"Embedding provider: BGE ({model_id})")
    else:
        if not user_api_config.get("api_key"):
            print("Embedding provider: OpenAI (no API key configured)")
            return
        try:
            client = get_client()
            model = user_api_config.get("embedding_model", "text-embedding-ada-002")
            manager.configure_openai(client=client, model=model)
            print(f"Embedding provider: OpenAI ({model})")
        except Exception as e:
            print(f"Embedding provider init failed: {e}")


def get_embedding_status():
    """获取当前嵌入提供者状态"""
    manager = EmbeddingManager()
    provider = manager.provider

    if provider is None:
        return {"provider_name": None, "model_name": None, "status": "not_configured"}

    result = {"provider_name": provider.provider_name, "model_name": provider.model_name}
    if isinstance(provider, BGEEmbeddingProvider):
        result["status"] = provider.load_status
        result["error"] = provider.load_error
    else:
        result["status"] = "ready"
    return result
