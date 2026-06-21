# services/model_router.py — Task-aware Model Router
# Balances accuracy vs hardware (local) and accuracy vs tokens (cloud)

from dataclasses import dataclass
from typing import Dict, Optional, Literal
from config import user_api_config

TaskName = Literal["paragraph_translate", "epub_replace", "kb_build", "long_text_translate", "term_extract"]

@dataclass
class TaskProfile:
    """Per-task model profile"""
    task: TaskName
    # local constraints
    prefer_quant: str  # "4bit" | "8bit" | "fp16"
    max_context_chars: int
    temperature: float
    max_output_tokens: int
    # cloud constraints
    cloud_model_tier: str  # "quality" | "balanced" | "fast"
    token_budget: int

# Frequency-driven profiles
TASK_PROFILES: Dict[TaskName, TaskProfile] = {
    # High frequency - paragraph translate: accurate + consistent, control tokens
    "paragraph_translate": TaskProfile(
        task="paragraph_translate",
        prefer_quant="4bit",
        max_context_chars=6000,
        temperature=0.1,
        max_output_tokens=1500,
        cloud_model_tier="balanced",
        token_budget=2500,
    ),
    # High frequency - epub replace: deterministic, structure preserving
    "epub_replace": TaskProfile(
        task="epub_replace",
        prefer_quant="4bit",
        max_context_chars=8000,
        temperature=0.0,
        max_output_tokens=4096,
        cloud_model_tier="quality",
        token_budget=6000,
    ),
    # Medium - KB construction
    "kb_build": TaskProfile(
        task="kb_build",
        prefer_quant="8bit",  # allow higher accuracy, less frequent
        max_context_chars=4000,
        temperature=0.2,
        max_output_tokens=800,
        cloud_model_tier="fast",
        token_budget=1500,
    ),
    # Low - long text
    "long_text_translate": TaskProfile(
        task="long_text_translate",
        prefer_quant="4bit",
        max_context_chars=8000,
        temperature=0.15,
        max_output_tokens=2048,
        cloud_model_tier="balanced",
        token_budget=3500,
    ),
    "term_extract": TaskProfile(
        task="term_extract",
        prefer_quant="4bit",
        max_context_chars=2000,
        temperature=0.0,
        max_output_tokens=512,
        cloud_model_tier="fast",
        token_budget=800,
    ),
}

# Cloud model tier mapping -> actual model id (token/cost aware)
CLOUD_MODEL_MAP = {
    "quality": "gpt-4o",
    "balanced": "gpt-4o-mini",
    "fast": "gpt-3.5-turbo",
}

# Local model tier mapping -> quantization + model_id fallback
LOCAL_MODEL_TIERS = {
    "quality": {"quant": "8bit", "model_fallback": "Qwen/Qwen2.5-7B-Instruct"},
    "balanced": {"quant": "4bit", "model_fallback": "Qwen/Qwen2-7B-Instruct"},
    "fast": {"quant": "4bit", "model_fallback": "Qwen/Qwen1.5-1.8B-Chat"},
}

class ModelRouter:
    """Central router: task -> provider + model + generation config"""
    
    @staticmethod
    def get_profile(task: TaskName) -> TaskProfile:
        return TASK_PROFILES.get(task, TASK_PROFILES["paragraph_translate"])
    
    @staticmethod
    def resolve_provider(task: TaskName, user_override: Optional[str] = None) -> Dict:
        """
        Returns:
          {
            "provider": "openai" | "local",
            "model": "...",
            "temperature": float,
            "max_tokens": int,
            "context_chars": int,
            "token_budget": int,
          }
        """
        profile = ModelRouter.get_profile(task)
        provider = user_override or user_api_config.get("llm_provider", "openai")
        
        if provider == "local":
            # hardware-aware: auto downgrade if low VRAM hint
            quant = profile.prefer_quant
            # allow env override
            if user_api_config.get("local_load_in_4bit"):
                quant = "4bit"
            elif user_api_config.get("local_load_in_8bit"):
                quant = "8bit"
            model_id = user_api_config.get("local_translate_model", "Qwen/Qwen2-7B-Instruct")
            return {
                "provider": "local",
                "model": model_id,
                "quant": quant,
                "temperature": profile.temperature,
                "max_tokens": profile.max_output_tokens,
                "context_chars": profile.max_context_chars,
                "token_budget": profile.token_budget,
            }
        else:
            # cloud: balance accuracy vs token cost
            tier = profile.cloud_model_tier
            model = CLOUD_MODEL_MAP[tier]
            # allow user override model_name
            model = user_api_config.get("model_name") or model
            return {
                "provider": "openai",
                "model": model,
                "temperature": profile.temperature,
                "max_tokens": profile.max_output_tokens,
                "context_chars": 30000 if "gpt-4" in model else 12000,
                "token_budget": profile.token_budget,
            }
    
    @staticmethod
    def get_generation_kwargs(task: TaskName, **overrides) -> Dict:
        cfg = ModelRouter.resolve_provider(task)
        base = {
            "temperature": cfg["temperature"],
            "max_tokens": cfg["max_tokens"],
            "top_p": 0.95 if cfg["temperature"] > 0 else 1.0,
        }
        base.update(overrides)
        return base

# singleton
model_router = ModelRouter()
