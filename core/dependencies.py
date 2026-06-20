# core/dependencies.py — 依赖注入与自定义异常
# 模块职责：API 客户端创建、模型配置、LLM 提供者同步、业务异常类

from openai import OpenAI
from config import user_api_config


# ---- 自定义异常 ----
class ConfigError(Exception):
    """配置相关错误（缺失 API key 等）"""
    pass


class KnowledgeError(Exception):
    """知识库操作错误"""
    pass


# ---- 客户端工厂 ----
def get_client():
    """获取 OpenAI 客户端实例。若未配置 API key 则抛出 ConfigError。"""
    if not user_api_config.get("api_key"):
        raise ConfigError("请先配置API密钥")
    return OpenAI(
        api_key=user_api_config["api_key"],
        base_url=user_api_config.get("base_url", "https://api.openai.com/v1")
    )


def get_model_config():
    """获取当前对话模型配置"""
    return {
        "model": user_api_config.get("model_name", "gpt-4-turbo-preview"),
        "embedding_model": user_api_config.get("embedding_model", "text-embedding-ada-002"),
    }


def sync_llm_manager():
    """根据 user_api_config 同步 LLMManager（类似 sync_embedding_manager）"""
    from model_providers import LLMManager

    manager = LLMManager()
    provider_type = user_api_config.get("llm_provider", "openai")

    if provider_type == "local":
        translate_model = user_api_config.get("local_translate_model", "Qwen/Qwen2-7B-Instruct-GPTQ-Int4")
        epub_model = user_api_config.get("local_epub_model", "") or translate_model
        load_in_4bit = user_api_config.get("local_load_in_4bit", True)
        load_in_8bit = user_api_config.get("local_load_in_8bit", False)

        from model_providers import TransformersLLMProvider
        trans_provider = TransformersLLMProvider(translate_model,
                                                  load_in_8bit=load_in_8bit,
                                                  load_in_4bit=load_in_4bit)
        manager.set_provider("translate", trans_provider)
        manager.set_provider("default", trans_provider)

        if epub_model != translate_model:
            epub_provider = TransformersLLMProvider(epub_model,
                                                     load_in_8bit=load_in_8bit,
                                                     load_in_4bit=load_in_4bit)
            manager.set_provider("epub", epub_provider)
        else:
            manager.set_provider("epub", trans_provider)

        mode = "4-bit GPTQ" if load_in_4bit else ("8-bit" if load_in_8bit else "FP16")
        print(f"LLM provider: Local (translate={translate_model}, epub={epub_model}, {mode})")
    else:
        if not user_api_config.get("api_key"):
            print("LLM provider: OpenAI (no API key configured)")
            return
        try:
            client = get_client()
            model = user_api_config.get("model_name", "gpt-4-turbo-preview")
            manager.configure_openai(client, model, task="translate")
            manager.configure_openai(client, model, task="epub")
            manager.configure_openai(client, model, task="default")
            print(f"LLM provider: OpenAI ({model})")
        except Exception as e:
            print(f"LLM provider init failed: {e}")

