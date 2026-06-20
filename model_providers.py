# model_providers.py — LLM 提供者抽象层
# 支持 OpenAI API 和本地 transformers 模型，复用 EmbeddingProvider 的惰性加载 + 线程安全模式

import threading
import gc
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

def cleanup_vram():
    """彻底清理 PyTorch / Python 显存碎片与残留对象"""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


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

    def __init__(self, model_id: str, device: str = None, load_in_8bit: bool = False,
                 load_in_4bit: bool = False):
        """
        Args:
            model_id: HuggingFace 模型 ID
            device: None=auto, 'cpu', 'cuda', 'cuda:0'
            load_in_8bit: 是否使用 8bit 量化（节省约 50% 内存）
            load_in_4bit: 是否使用 4bit 量化（GPTQ 模型专用，显存约 4GB）
        """
        self._model_id = model_id
        self._device = device
        self._load_in_8bit = load_in_8bit
        self._load_in_4bit = load_in_4bit
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
                import torch
                
                # 检查 PyTorch 是否支持 CUDA 显卡加速
                if not torch.cuda.is_available():
                    print("\n" + "="*80)
                    print("⚠️ [特别警告] 当前安装的 PyTorch 不支持 CUDA 显卡加速 (torch.cuda.is_available() 为 False)！")
                    print("模型被迫以纯 CPU 运行，这将占用高达 6GB 以上的系统内存 (RAM)，且显卡利用率将为 0%！")
                    print("请在终端运行以下命令安装 GPU 显卡加速版本的 PyTorch：")
                    print("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
                    print("="*80 + "\n")
                    target_device = "cpu"
                else:
                    if self._device is None or self._device == "auto":
                        target_device = "cuda:0"
                    else:
                        target_device = self._device

                load_kwargs = {
                    "device_map": target_device,
                    "trust_remote_code": True,
                    "low_cpu_mem_usage": True,  # 彻底避免将完整的 Tensors 缓存在 CPU 系统内存中，大幅降低 RAM 内存压力
                    "attn_implementation": "sdpa"  # 开启 PyTorch 原生高效注意力 (Flash Attention / SDPA)，彻底解决输入长文本时 N^2 显存分配导致 OOM (9.88GB) 的问题
                }

                # 4-bit GPTQ 量化模型（如 Qwen2-7B-Instruct-GPTQ-Int4）
                if self._load_in_4bit:
                    load_kwargs.pop("attn_implementation", None)  # GPTQ 可能不支持 sdpa
                    print(f"[Model] Loading 4-bit GPTQ model: {self._model_id}")
                    self._model = AutoModelForCausalLM.from_pretrained(
                        self._model_id,
                        device_map="auto",
                        trust_remote_code=True,
                        low_cpu_mem_usage=True,
                        torch_dtype=torch.float16,
                    )
                    self._model.eval()  # GPTQ 推理模式
                elif self._load_in_8bit:
                    load_kwargs["load_in_8bit"] = True
                    self._model = AutoModelForCausalLM.from_pretrained(
                        self._model_id, **load_kwargs
                    )
                else:
                    load_kwargs["torch_dtype"] = torch.float16
                    self._model = AutoModelForCausalLM.from_pretrained(
                        self._model_id, **load_kwargs
                    )
                
                # 再次强制确保模型完整挂载在 GPU 显卡显存上
                if target_device != "cpu":
                    try:
                        self._model.to(target_device)
                    except Exception:
                        pass
                        
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

        try:
            # 构建输入
            prompt = self._build_prompt(messages)
            # 极度安全保险：如果构建的总 Prompt 超过 5000 字符，强制做合理的中间截断保留（重点确保首部 System 学术规范和尾部 User 待译文本完整），防止 RAG/TM 拼接过长导致向前传播时中间层激活 Tensor 发生 $O(N^2)$ 爆炸产生显存 OOM
            if len(prompt) > 5000:
                prompt = prompt[:2000] + "\n\n... [参考上文已智能截断] ...\n\n" + prompt[-2500:]
                
            inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
    
            # 生成参数
            temperature = gen_kwargs.get("temperature", 0.3)
            max_new_tokens = gen_kwargs.get("max_tokens") or gen_kwargs.get("max_new_tokens", 2048)
            top_p = gen_kwargs.get("top_p", 0.9)
    
            import torch
            with torch.inference_mode():
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
        except BaseException as e:
            cleanup_vram()
            if "out of memory" in str(e).lower():
                raise RuntimeError("❌ 显卡显存溢出 (CUDA Out Of Memory)！已为您紧急清理并释放显存缓存。请尝试缩短本次提交的英文段落或 EPUB 代码篇幅后再试。")
            raise e
        finally:
            # 每次生成完毕，立刻深度清理残留的隐式 Tensors 和计算图
            cleanup_vram()


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
                        device: str = None, load_in_8bit: bool = False,
                        load_in_4bit: bool = False):
        """配置本地模型（支持 4-bit GPTQ / 8-bit 量化）"""
        self.set_provider(task,
                          TransformersLLMProvider(model_id, device=device,
                                                  load_in_8bit=load_in_8bit,
                                                  load_in_4bit=load_in_4bit))

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

    def preload_local_models(self):
        """异步在后台触发本地模型的惰性加载"""
        with self._provider_lock:
            for task, provider in self._providers.items():
                if isinstance(provider, TransformersLLMProvider):
                    threading.Thread(target=provider._ensure_model_loaded).start()
