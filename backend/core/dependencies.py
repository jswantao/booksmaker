# core/dependencies.py — v3
from openai import OpenAI
from config import user_api_config

class ConfigError(Exception): pass

def get_client():
    if not user_api_config.get("api_key"):
        raise ConfigError("请先配置API密钥")
    return OpenAI(api_key=user_api_config["api_key"], base_url=user_api_config.get("base_url", "https://api.openai.com/v1"))

def sync_llm_manager():
    """Sync LLMManager based on user_api_config.llm_provider (user independent choice)"""
    from model_providers import LLMManager, LLMConfig, ModelLoadConfig
    manager = LLMManager()
    provider_type = user_api_config.get("llm_provider", "openai")

    if provider_type == "local":
        model_id = user_api_config.get("local_translate_model", "Qwen/Qwen2-7B-Instruct")
        load_cfg = ModelLoadConfig(
            load_in_4bit=user_api_config.get("local_load_in_4bit", True),
            load_in_8bit=user_api_config.get("local_load_in_8bit", False),
            download_source=user_api_config.get("download_source", "huggingface"),
            cache_dir=user_api_config.get("modelscope_cache_dir", "./models")
        )
        # Configure for all 4 task slots
        for task in ["paragraph_translate","epub_replace","kb_build","long_text_translate","translate","default","epub"]:
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
