# model_providers.py — LLM 提供者抽象层
# 支持 OpenAI API 和本地 transformers 模型，复用 EmbeddingProvider 的惰性加载 + 线程安全模式

import threading
from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class LLMProvider(ABC):
    """LLM 提供者抽象基类"""

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **gen_kwargs) -> str:
        """生成回复

        Args:
            messages: OpenAI 格式的消息列表 [{"role":"system","content":...}, ...]
            **gen_kwargs: temperature, max_tokens 等生成参数

        Returns:
            模型生成的文本回复
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供者唯一标识"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """当前使用的模型名称"""
        ...


# ==================== OpenAI LLM 提供者 ====================
class OpenAILLMProvider(LLMProvider):
    """封装 OpenAI chat.completions.create()"""

    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    @property
    def provider_name(self) -> str: return "openai"

    @property
    def model_name(self) -> str: return self._model

    def chat(self, messages: List[Dict[str, str]], **gen_kwargs) -> str:
        # 过滤掉 transformers 专用参数
        kwargs = {k: v for k, v in gen_kwargs.items() if k in ("temperature", "max_tokens", "top_p")}
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content


# ==================== Transformers 本地 LLM 提供者 ====================
class TransformersLLMProvider(LLMProvider):
    """封装本地 transformers 模型推理，惰性加载 + 线程安全"""

    def __init__(self, model_id: str, device: str = None, load_in_8bit: bool = True):
        """
        Args:
            model_id: HuggingFace 模型 ID
            device: None=auto, 'cpu', 'cuda', 'cuda:0'
            load_in_8bit: 是否使用 8bit 量化（节省约 50% 内存）
        """
        self._model_id = model_id
        self._device = device
        self._load_in_8bit = load_in_8bit
        self._model = None
        self._tokenizer = None
        self._load_error: Optional[str] = None
        self._load_status: str = "idle"
        self._load_lock = threading.Lock()

    @property
    def provider_name(self) -> str: return "local"

    @property
    def model_name(self) -> str: return self._model_id

    @property
    def load_status(self) -> str: return self._load_status

    @property
    def load_error(self) -> Optional[str]: return self._load_error

    def _ensure_model_loaded(self):
        """惰性加载模型（首次调用时触发），线程安全双检锁"""
        if self._model is not None:
            return
        with self._load_lock:
            if self._model is not None:
                return
            if self._load_error:
                self._load_error = None
                self._load_status = "idle"

            self._load_status = "downloading"
            try:
                from transformers import AutoModelForCausalLM, AutoTokenizer

                self._load_status = "loading"
                # 加载 tokenizer
                self._tokenizer = AutoTokenizer.from_pretrained(
                    self._model_id, trust_remote_code=True
                )
                # 确保有 padding token
                if self._tokenizer.pad_token is None:
                    self._tokenizer.pad_token = self._tokenizer.eos_token

                # 加载模型
                load_kwargs = {"device_map": "auto" if self._device is None else self._device,
                               "trust_remote_code": True}
                if self._load_in_8bit:
                    load_kwargs["load_in_8bit"] = True
                else:
                    load_kwargs["torch_dtype"] = "auto"

                self._model = AutoModelForCausalLM.from_pretrained(
                    self._model_id, **load_kwargs
                )
                self._load_status = "ready"
            except ImportError as e:
                self._load_error = f"缺少依赖: {e}。请运行 pip install transformers accelerate bitsandbytes"
                self._load_status = "error"
                raise RuntimeError(self._load_error)
            except Exception as e:
                self._load_error = str(e)
                self._load_status = "error"
                raise RuntimeError(f"无法加载模型 '{self._model_id}': {e}")

    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        """将 OpenAI 格式消息转换为模型输入文本。

        使用 ChatML 格式（Qwen 等模型原生支持），也兼容通用格式。
        """
        parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                parts.append(f"<|system|>\n{content}</s>")
            elif role == "user":
                parts.append(f"<|user|>\n{content}</s>")
            elif role == "assistant":
                parts.append(f"<|assistant|>\n{content}</s>")
        parts.append("<|assistant|>\n")
        return "\n".join(parts)

    def chat(self, messages: List[Dict[str, str]], **gen_kwargs) -> str:
        self._ensure_model_loaded()

        # 构建输入
        prompt = self._build_prompt(messages)
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)

        # 生成参数
        temperature = gen_kwargs.get("temperature", 0.3)
        max_new_tokens = gen_kwargs.get("max_tokens") or gen_kwargs.get("max_new_tokens", 2048)
        top_p = gen_kwargs.get("top_p", 0.9)

        outputs = self._model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature if temperature > 0 else 1.0,
            do_sample=temperature > 0,
            top_p=top_p,
            pad_token_id=self._tokenizer.pad_token_id,
            eos_token_id=self._tokenizer.eos_token_id,
        )

        # 解码（仅保留新生成部分）
        response = self._tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:],
            skip_special_tokens=True
        )
        return response.strip()


# ==================== LLM 管理器（单例） ====================
class LLMManager:
    """单例管理器，支持 per-task 模型选择，线程安全"""

    _instance: Optional["LLMManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._providers: Dict[str, LLMProvider] = {}
                    obj._default_task = "default"
                    obj._provider_lock = threading.RLock()
                    cls._instance = obj
        return cls._instance

    def set_provider(self, task: str, provider: LLMProvider):
        with self._provider_lock:
            self._providers[task] = provider

    def get_provider(self, task: str = "default") -> Optional[LLMProvider]:
        with self._provider_lock:
            # 精确匹配 → fallback "default" → 第一个可用
            return self._providers.get(task) or self._providers.get("default") or (
                next(iter(self._providers.values())) if self._providers else None)

    def configure_openai(self, client, model: str, task: str = "default"):
        """配置 OpenAI 模式（所有任务共用同一模型）"""
        self.set_provider(task, OpenAILLMProvider(client, model))

    def configure_local(self, model_id: str, task: str = "default",
                        device: str = None, load_in_8bit: bool = True):
        """配置本地模型"""
        self.set_provider(task,
                          TransformersLLMProvider(model_id, device=device, load_in_8bit=load_in_8bit))

    def chat(self, messages: List[Dict[str, str]], task: str = "default", **gen_kwargs) -> str:
        """统一生成接口，根据 task 选择对应模型"""
        provider = self.get_provider(task)
        if provider is None:
            raise RuntimeError("未配置 LLM 提供者，请先配置 API 密钥或选择本地模型")
        return provider.chat(messages, **gen_kwargs)

    def get_all_status(self) -> Dict:
        """返回所有任务的模型状态"""
        with self._provider_lock:
            result = {}
            for task, provider in self._providers.items():
                status_info = {"provider_name": provider.provider_name, "model_name": provider.model_name}
                if isinstance(provider, TransformersLLMProvider):
                    status_info["status"] = provider.load_status
                    status_info["error"] = provider.load_error
                else:
                    status_info["status"] = "ready"
                result[task] = status_info
            return result
