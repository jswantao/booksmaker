# core/dependencies.py — v3
from openai import OpenAI
from config import user_api_config

class ConfigError(Exception): pass

def get_client():
    if not user_api_config.get("api_key"):
        raise ConfigError("请先配置API密钥")
    return OpenAI(api_key=user_api_config["api_key"], base_url=user_api_config.get("base_url", "https://api.openai.com/v1"))

def sync_llm_manager():
    """Sync LLMManager based on user_api_config.llm_provider.
    
    优化：跳过已有相同模型的 provider 重建，避免不必要的 GPU 模型卸载/重载。
    """
    from model_providers import LLMManager, LLMConfig, ModelLoadConfig, TransformersLLMProvider
    from config import MODELS_CACHE_DIR
    manager = LLMManager()
    provider_type = user_api_config.get("llm_provider", "openai")

    if provider_type == "local":
        model_id = user_api_config.get("local_translate_model", "Qwen/Qwen2-7B-Instruct")
        load_cfg = ModelLoadConfig(
            load_in_4bit=user_api_config.get("local_load_in_4bit", True),
            load_in_8bit=user_api_config.get("local_load_in_8bit", False),
            download_source=user_api_config.get("download_source", "huggingface"),
            cache_dir=user_api_config.get("modelscope_cache_dir", MODELS_CACHE_DIR)
        )
        tasks = ["paragraph_translate","epub_replace","kb_build","long_text_translate","translate","default","epub"]
        for task in tasks:
            # 跳过已有相同模型的 provider，避免 cleanup + 重新加载
            existing = manager.get_provider(task)
            if (isinstance(existing, TransformersLLMProvider)
                    and existing.model_name == model_id
                    and existing.load_status in ("ready", "idle", "loading_tokenizer", "loading_model")):
                continue
            try:
                manager.configure_local(model_id, task=task, load_config=load_cfg,
                    llm_config=LLMConfig(temperature=0.2, max_tokens=2048))
            except Exception as e:
                print(f"local configure {task} failed: {e}")
        print(f"LLM provider: Local ({model_id})")
    else:
        if not user_api_config.get("api_key"):
            print("LLM provider: OpenAI (no API key)")
            return
        try:
            client = get_client()
            model = user_api_config.get("model_name", "gpt-4o-mini")
            for task in ["paragraph_translate","epub_replace","kb_build","long_text_translate","translate","default","epub"]:
                manager.configure_openai(client, model, task=task)
            print(f"LLM provider: OpenAI ({model})")
        except Exception as e:
            print(f"LLM provider init failed: {e}")
