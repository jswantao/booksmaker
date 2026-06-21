# utils/cuda.py — 公共 GPU 显存管理工具
# 消除 model_providers / embedding_providers / translation_pipeline 中的重复 _cleanup_vram 定义

import gc


def cleanup_vram():
    """彻底清理 PyTorch 显存碎片和缓存。

    仅在使用本地 GPU 模型时有意义；云端 API 调用时无需调用。
    """
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:
        pass


def is_local_provider() -> bool:
    """判断当前 LLM 提供者是否为本地模型"""
    try:
        from config import user_api_config
        return user_api_config.get("llm_provider") == "local"
    except Exception:
        return False


def cleanup_if_local():
    """仅在本地模型时清理 VRAM（云端 API 自动跳过）"""
    if is_local_provider():
        cleanup_vram()
