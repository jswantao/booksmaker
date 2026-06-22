# model_providers.py — LLM 提供者抽象层（优化版）
# 支持 OpenAI API 和本地 transformers 模型，采用惰性加载 + 线程安全模式

import os
import re
import threading
import time
import gc
from pathlib import Path
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any, Tuple

from utils.cuda import cleanup_vram


# ==================== 异常定义 ====================
class LLMError(Exception):
    """LLM 处理异常"""
    pass


class ModelLoadError(LLMError):
    """模型加载异常"""
    pass


class ProviderNotConfiguredError(LLMError):
    """提供者未配置异常"""
    pass


class GenerationError(LLMError):
    """生成异常"""
    pass


class OutOfMemoryError(LLMError):
    """显存/内存不足异常"""
    pass


# ==================== 配置数据类 ====================
@dataclass
class LLMConfig:
    """LLM 生成配置"""
    temperature: float = 0.3
    max_tokens: int = 2048
    top_p: float = 0.9
    top_k: int = 50
    repetition_penalty: float = 1.1
    
    # 上下文管理
    max_context_chars: int = 8000
    reserved_output_chars: int = 2000
    
    # 重试配置
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class ModelLoadConfig:
    """模型加载配置"""
    device: Optional[str] = None
    load_in_8bit: bool = False
    load_in_4bit: bool = False
    download_source: str = "huggingface"  # "huggingface" | "modelscope"
    cache_dir: str = ""  # 空字符串表示使用 config.py 中设置的 HF_HOME/MODELSCOPE_CACHE_DIR
    trust_remote_code: bool = True
    low_cpu_mem_usage: bool = True
    attn_implementation: str = "sdpa"  # "sdpa" | "flash_attention_2" | "eager"
    torch_dtype: str = "auto"  # "auto" | "float16" | "bfloat16" | "float32"


# ==================== 抽象基类 ====================
class LLMProvider(ABC):
    """LLM 提供者抽象基类"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **gen_kwargs) -> str:
        """生成回复

        Args:
            messages: OpenAI 格式的消息列表
            **gen_kwargs: temperature, max_tokens 等生成参数

        Returns:
            模型生成的文本回复
        """
        ...

    def chat_stream(self, messages: List[Dict[str, str]], **gen_kwargs):
        """流式生成回复（默认实现：一次性返回 chat() 结果）

        Yields:
            str: 增量文本片段
        """
        yield self.chat(messages, **gen_kwargs)

    def chat_with_retry(self, messages: List[Dict[str, str]], **gen_kwargs) -> str:
        """带重试机制的聊天接口"""
        max_retries = gen_kwargs.pop('max_retries', self.config.max_retries)
        retry_delay = gen_kwargs.pop('retry_delay', self.config.retry_delay)
        
        last_error = None
        for attempt in range(max_retries):
            try:
                return self.chat(messages, **gen_kwargs)
            except OutOfMemoryError:
                raise  # OOM 不重试
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))  # 指数退避
                    cleanup_vram()
                    continue
        
        raise GenerationError(f"生成失败 (重试 {max_retries} 次): {last_error}")

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

    @property
    def status(self) -> str:
        """提供者状态"""
        return "ready"

    def warm_up(self):
        """模型预热（子类可重写）"""
        pass

    def cleanup(self):
        """资源清理（子类可重写）"""
        pass


# ==================== OpenAI LLM 提供者 ====================
class OpenAILLMProvider(LLMProvider):
    """封装 OpenAI chat.completions.create()（优化版）"""

    # OpenAI 支持的参数白名单
    ALLOWED_PARAMS = {"temperature", "max_tokens", "top_p", "frequency_penalty", 
                      "presence_penalty", "seed", "stop"}

    # 模型上下文长度映射
    CONTEXT_LENGTH_MAP = {
        "gpt-3.5-turbo": 4096,
        "gpt-3.5-turbo-16k": 16384,
        "gpt-4": 8192,
        "gpt-4-32k": 32768,
        "gpt-4-turbo": 128000,
        "gpt-4o": 128000,
    }

    def __init__(self, client, model: str, config: Optional[LLMConfig] = None):
        """
        Args:
            client: OpenAI 客户端实例
            model: 模型名称
            config: LLM 配置
        """
        super().__init__(config)
        self._client = client
        self._model = model
        self._context_length = self.CONTEXT_LENGTH_MAP.get(model, 4096)

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_length(self) -> int:
        """模型上下文长度"""
        return self._context_length

    def _filter_params(self, gen_kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """过滤并规范化生成参数"""
        filtered = {}
        
        # 温度处理
        if "temperature" in gen_kwargs:
            temperature = gen_kwargs["temperature"]
            if temperature <= 0:
                # OpenAI 不支持 temperature=0，使用极小值代替
                filtered["temperature"] = 0.01
            else:
                filtered["temperature"] = temperature
        
        # 其他参数
        for key in self.ALLOWED_PARAMS:
            if key in gen_kwargs and key != "temperature":
                filtered[key] = gen_kwargs[key]
        
        return filtered

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """粗略估算消息的 token 数量"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            # 粗略估算：中文约1.5字符/token，英文约4字符/token
            total += len(content) // 3 + 1
        return total

    def chat(self, messages: List[Dict[str, str]], **gen_kwargs) -> str:
        """调用 OpenAI API 生成回复"""
        if not messages:
            raise ValueError("消息列表不能为空")

        # 估算 token 数量并警告
        estimated_tokens = self._estimate_tokens(messages)
        if estimated_tokens > self._context_length * 0.8:
            print(f"⚠️ 警告: 输入约 {estimated_tokens} tokens，接近模型限制 {self._context_length}")

        # 合并配置和运行时参数
        merged_kwargs = {
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
        }
        merged_kwargs.update(gen_kwargs)
        
        # 过滤参数
        kwargs = self._filter_params(merged_kwargs)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                **kwargs
            )
            return response.choices[0].message.content
        except Exception as e:
            error_msg = str(e).lower()
            if "context_length" in error_msg or "maximum context" in error_msg:
                raise LLMError(f"上下文超长: {e}. 请缩短输入或使用更长的模型。")
            raise LLMError(f"OpenAI API 调用失败: {e}")

    def chat_stream(self, messages: List[Dict[str, str]], **gen_kwargs):
        """流式调用 OpenAI API，逐 chunk yield 增量文本"""
        if not messages:
            raise ValueError("消息列表不能为空")

        merged_kwargs = {
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
        }
        merged_kwargs.update(gen_kwargs)
        kwargs = self._filter_params(merged_kwargs)

        try:
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                stream=True,
                **kwargs
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            error_msg = str(e).lower()
            if "context_length" in error_msg or "maximum context" in error_msg:
                raise LLMError(f"上下文超长: {e}. 请缩短输入或使用更长的模型。")
            raise LLMError(f"OpenAI API 流式调用失败: {e}")

    def warm_up(self):
        """预热：发送测试请求"""
        try:
            self.chat([{"role": "user", "content": "test"}], max_tokens=1)
        except Exception:
            pass


# ==================== Transformers 本地 LLM 提供者 ====================
class TransformersLLMProvider(LLMProvider):
    """封装本地 transformers 模型推理（优化版）

    特性:
    - 惰性加载 + 线程安全
    - 支持 4-bit/8-bit 量化
    - ModelScope/HuggingFace 双源下载
    - 智能 Prompt 构建（Qwen/Hunyuan/ChatML）
    - 上下文预算管理
    """

    # ModelScope ID 映射表 (HF → ModelScope)
    MODELSCOPE_MAPPING = {
        # Qwen3.5 系列 (最新)
        "Qwen/Qwen3.5-4B": "qwen/Qwen3.5-4B",
        "Qwen/Qwen3.5-8B": "qwen/Qwen3.5-8B",
        # Qwen2.5 系列
        "Qwen/Qwen2.5-7B-Instruct": "qwen/Qwen2.5-7B-Instruct",
        "Qwen/Qwen2.5-3B-Instruct": "qwen/Qwen2.5-3B-Instruct",
        "Qwen/Qwen2.5-1.5B-Instruct": "qwen/Qwen2.5-1.5B-Instruct",
        "Qwen/Qwen2.5-0.5B-Instruct": "qwen/Qwen2.5-0.5B-Instruct",
        "Qwen/Qwen2.5-14B-Instruct": "qwen/Qwen2.5-14B-Instruct",
        # Qwen2 系列
        "Qwen/Qwen2-7B-Instruct": "qwen/Qwen2-7B-Instruct",
        "Qwen/Qwen2-1.5B-Instruct": "qwen/Qwen2-1.5B-Instruct",
        # ChatGLM 系列
        "THUDM/chatglm3-6b": "ZhipuAI/chatglm3-6b",
        "THUDM/chatglm4-1.5b": "ZhipuAI/chatglm4-1.5b",
        # InternLM 系列
        "internlm/internlm2-chat-7b": "Shanghai_AI_Laboratory/internlm2-chat-7b",
        "internlm/internlm2-chat-1_8b": "Shanghai_AI_Laboratory/internlm2-chat-1_8b",
        # DeepSeek 系列
        "deepseek-ai/deepseek-coder-6.7b-instruct": "deepseek-ai/deepseek-coder-6.7b-instruct",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        # Hunyuan 系列
        "tencent/Hunyuan-7B-Instruct": None,
        "Tencent-Hunyuan/Hunyuan-MT-7B": "Tencent-Hunyuan/Hunyuan-MT-7B",
        # Hy-MT2 系列 (混元翻译二代)
        "Tencent-Hunyuan/Hy-MT2-1.8B": "Tencent-Hunyuan/Hy-MT2-1.8B",
    }

    def __init__(self, model_id: str, load_config: Optional[ModelLoadConfig] = None,
                 llm_config: Optional[LLMConfig] = None):
        """
        Args:
            model_id: HuggingFace 模型 ID
            load_config: 模型加载配置
            llm_config: LLM 生成配置
        """
        super().__init__(llm_config)
        self._model_id = self._sanitize_model_id(model_id)
        self._load_config = load_config or ModelLoadConfig()
        
        # 状态管理
        self._model = None
        self._tokenizer = None
        self._model_path: Optional[str] = None
        self._load_error: Optional[str] = None
        self._load_status: str = "idle"
        self._load_lock = threading.Lock()
        self._model_family: Optional[str] = None
        
        # 性能统计
        self._generation_count: int = 0
        self._total_tokens_generated: int = 0

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def model_name(self) -> str:
        return self._model_id

    @property
    def load_status(self) -> str:
        return self._load_status

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error

    @property
    def status(self) -> str:
        if self._load_status == "error":
            return f"error: {self._load_error}"
        return self._load_status

    @property
    def stats(self) -> Dict[str, Any]:
        """返回性能统计"""
        return {
            "generation_count": self._generation_count,
            "total_tokens_generated": self._total_tokens_generated,
        }

    # ========== 模型 ID 处理 ==========
    @staticmethod
    def _sanitize_model_id(model_id: str) -> str:
        """清理模型 ID"""
        mid = model_id.strip().rstrip('/')
        if mid.startswith('/'):
            mid = mid[1:]
        parts = mid.split('/')
        parts = [p.strip() for p in parts if p.strip()]
        return '/'.join(parts) if len(parts) >= 2 else mid

    def _detect_model_family(self) -> str:
        """检测模型家族"""
        if self._model_family is not None:
            return self._model_family
            
        lid = self._model_id.lower()
        if 'qwen' in lid:
            self._model_family = 'qwen'
        elif 'hunyuan' in lid:
            self._model_family = 'hunyuan'
        elif 'llama' in lid or 'vicuna' in lid or 'alpaca' in lid:
            self._model_family = 'llama'
        elif 'chatglm' in lid:
            self._model_family = 'chatglm'
        elif 'mistral' in lid:
            self._model_family = 'mistral'
        else:
            self._model_family = 'generic'
        
        return self._model_family

    # ========== 模型加载 ==========
    def _ensure_model_loaded(self):
        """惰性加载模型（线程安全双检锁）"""
        if self._model is not None:
            return

        with self._load_lock:
            if self._model is not None:
                return

            # 重置错误状态
            if self._load_error:
                self._load_error = None
                self._load_status = "idle"

            try:
                self._load_model()
            except ImportError as e:
                self._load_error = self._get_import_hint(str(e))
                self._load_status = "error"
                raise ModelLoadError(self._load_error)
            except Exception as e:
                self._load_error = str(e)
                self._load_status = "error"
                raise ModelLoadError(f"无法加载模型 '{self._model_id}': {e}")

    def _get_import_hint(self, error_msg: str) -> str:
        """根据错误信息生成安装提示"""
        if "transformers" in error_msg:
            return "请安装 transformers: pip install transformers"
        if "bitsandbytes" in error_msg:
            return "请安装 bitsandbytes: pip install bitsandbytes"
        if "accelerate" in error_msg:
            return "请安装 accelerate: pip install accelerate"
        if "modelscope" in error_msg:
            return "请安装 modelscope: pip install modelscope"
        return f"缺少依赖: {error_msg}"

    def _load_model(self):
        """加载模型和分词器"""
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        # 1. 确定加载路径
        load_path = self._resolve_model_path()

        # 2. 加载分词器
        self._load_status = "loading_tokenizer"
        print(f"📝 加载分词器: {load_path}")
        self._tokenizer = AutoTokenizer.from_pretrained(
            load_path, 
            trust_remote_code=self._load_config.trust_remote_code
        )
        self._configure_tokenizer()

        # 3. 确定设备和数据类型
        device, torch_dtype = self._resolve_device_and_dtype()

        # 4. 构建加载参数
        load_kwargs = self._build_load_kwargs(device, torch_dtype)

        # 5. 加载模型
        self._load_status = "loading_model"
        print(f"🔄 加载模型: {load_path}")
        print(f"   设备: {device}, 数据类型: {torch_dtype}")
        
        if self._load_config.load_in_4bit:
            self._model = self._load_4bit_model(load_path, load_kwargs)
        elif self._load_config.load_in_8bit:
            load_kwargs["load_in_8bit"] = True
            self._model = AutoModelForCausalLM.from_pretrained(load_path, **load_kwargs)
        else:
            self._model = AutoModelForCausalLM.from_pretrained(load_path, **load_kwargs)

        # 5b. 自动加载 LoRA 适配器（如果存在）
        self._load_lora_if_present(load_path)

        # 6. 确保模型在正确设备上
        if device != "cpu":
            try:
                self._model.to(device)
            except Exception:
                pass

        self._load_status = "ready"
        
        # 打印模型信息
        self._print_model_info()

    def _resolve_model_path(self) -> str:
        """解析模型路径（本地 > ModelScope > HuggingFace）"""
        # 1. 检查本地缓存
        local_path = self._find_local_model()
        if local_path:
            return local_path

        # 2. 尝试 ModelScope 下载
        if self._load_config.download_source == "modelscope":
            self._load_status = "downloading"
            ms_path = self._try_modelscope_download()
            if ms_path:
                self._model_path = ms_path
                return ms_path
            print(f"⚠️ ModelScope 下载失败，回退到 HuggingFace")

        # 3. 使用 HuggingFace
        return self._model_id

    def _find_local_model(self) -> Optional[str]:
        """查找本地缓存的模型（搜索顺序：用户指定 → 合并模型 → 缓存目录 → 旧版目录）"""
        # 1. 检查用户指定路径
        custom_path = os.environ.get("LLM_MODEL_PATH")
        if custom_path and os.path.exists(custom_path):
            print(f"✅ 找到本地模型: {custom_path}")
            return custom_path

        # 2. 搜索模型缓存和合并模型目录
        from config import PROJECT_ROOT, MERGED_MODELS_DIR, LEGACY_MODELS_DIR
        search_dirs = []
        cache_dir = self._load_config.cache_dir
        if cache_dir:
            search_dirs.append(cache_dir)
        search_dirs.append(str(PROJECT_ROOT / "model_cache"))
        search_dirs.append(str(PROJECT_ROOT / "model_cache" / ".ms"))
        search_dirs.append(str(PROJECT_ROOT / "model_cache" / ".hf" / "hub"))
        # 合并后的模型目录（新路径 + 旧路径兼容）
        search_dirs.append(MERGED_MODELS_DIR)
        if os.path.isdir(LEGACY_MODELS_DIR):
            search_dirs.append(LEGACY_MODELS_DIR)

        for base_dir in search_dirs:
            if not os.path.isdir(base_dir):
                continue
            # ModelScope 格式
            ms_id = self.MODELSCOPE_MAPPING.get(self._model_id, self._model_id)
            ms_path = os.path.join(base_dir, ms_id)
            if os.path.isdir(ms_path) and os.path.exists(os.path.join(ms_path, "config.json")):
                print(f"✅ 找到本地模型: {ms_path}")
                return ms_path

            # HuggingFace 格式
            hf_name = f"models--{self._model_id.replace('/', '--')}"
            hf_path = os.path.join(base_dir, hf_name)
            snapshots_dir = os.path.join(hf_path, "snapshots")
            if os.path.isdir(snapshots_dir):
                for snapshot in sorted(os.listdir(snapshots_dir), reverse=True):
                    snapshot_path = os.path.join(snapshots_dir, snapshot)
                    if os.path.exists(os.path.join(snapshot_path, "config.json")):
                        print(f"✅ 找到本地模型: {snapshot_path}")
                        return snapshot_path

        return None

    def _try_modelscope_download(self) -> Optional[str]:
        """尝试从 ModelScope 下载模型"""
        try:
            from modelscope import snapshot_download
        except ImportError:
            print("⚠️ modelscope 未安装，跳过 ModelScope 下载")
            return None

        # 获取 ModelScope ID
        ms_id = self.MODELSCOPE_MAPPING.get(self._model_id)
        if ms_id is None:
            print(f"⚠️ ModelScope 上未找到模型 '{self._model_id}'")
            return None

        try:
            print(f"📥 ModelScope 下载: {ms_id}")
            cache_dir = self._load_config.cache_dir or None
            local_path = snapshot_download(ms_id, cache_dir=cache_dir)
            print(f"✅ ModelScope 下载完成: {local_path}")
            return local_path
        except Exception as e:
            print(f"⚠️ ModelScope 下载失败: {e}")
            return None

    def _resolve_device_and_dtype(self) -> Tuple[str, Any]:
        """确定设备和数据类型"""
        import torch
        
        # 检查 CUDA 可用性
        if not torch.cuda.is_available():
            print("\n" + "="*80)
            print("⚠️ [警告] PyTorch 不支持 CUDA，将使用 CPU 运行")
            print("   请安装 GPU 版本: pip install torch --index-url https://download.pytorch.org/whl/cu121")
            print("="*80 + "\n")
            return "cpu", torch.float32
        
        # 确定设备
        if self._load_config.device and self._load_config.device != "auto":
            device = self._load_config.device
        else:
            device = "cuda:0"
        
        # 确定数据类型
        dtype_str = self._load_config.torch_dtype
        if dtype_str == "float16":
            torch_dtype = torch.float16
        elif dtype_str == "bfloat16":
            torch_dtype = torch.bfloat16
        elif dtype_str == "float32":
            torch_dtype = torch.float32
        else:  # auto
            torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        
        return device, torch_dtype

    def _build_load_kwargs(self, device: str, torch_dtype: Any) -> Dict[str, Any]:
        """构建模型加载参数"""
        return {
            "device_map": device,
            "trust_remote_code": self._load_config.trust_remote_code,
            "low_cpu_mem_usage": self._load_config.low_cpu_mem_usage,
            "torch_dtype": torch_dtype,
        }

    def _load_4bit_model(self, load_path: str, base_kwargs: Dict[str, Any]):
        """加载 4-bit 量化模型"""
        from transformers import AutoModelForCausalLM, BitsAndBytesConfig
        import torch
        
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        base_kwargs["quantization_config"] = bnb_config
        
        print(f"📦 加载 4-bit 量化模型 (NF4)")
        return AutoModelForCausalLM.from_pretrained(load_path, **base_kwargs)

    def _load_lora_if_present(self, model_path: str):
        """检查并加载 LoRA 适配器（如果模型目录下存在 adapter_config.json）"""
        adapter_config = Path(model_path) / "adapter_config.json"
        adapter_model = Path(model_path) / "adapter_model.safetensors"
        # 也检查子目录（训练产出的标准结构）
        lora_final = Path(model_path) / "final" / "adapter_config.json"
        if lora_final.exists():
            adapter_config = lora_final
            adapter_model = Path(model_path) / "final" / "adapter_model.safetensors"

        if not adapter_config.exists():
            return  # 无 LoRA 适配器

        try:
            from peft import PeftModel
            print(f"🔗 加载 LoRA 适配器: {adapter_config.parent}")
            self._model = PeftModel.from_pretrained(self._model, adapter_config.parent)
            self._model = self._model.merge_and_unload()  # 合并进基础模型以加速推理
            print("✅ LoRA 适配器已合并")
        except ImportError:
            print("⚠️ peft 未安装，跳过 LoRA 加载 (pip install peft)")
        except Exception as e:
            print(f"⚠️ LoRA 加载失败: {e}")

    def _configure_tokenizer(self):
        """配置分词器"""
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token
        if self._tokenizer.pad_token_id is None:
            self._tokenizer.pad_token_id = self._tokenizer.eos_token_id

    def _print_model_info(self):
        """打印模型信息"""
        import torch
        
        model_size = sum(p.numel() for p in self._model.parameters()) / 1e9
        print(f"✅ 模型加载成功")
        print(f"   模型: {self._model_id}")
        print(f"   参数量: {model_size:.2f}B")
        print(f"   设备: {self._model.device}")
        print(f"   家族: {self._detect_model_family()}")

    # ========== Prompt 构建 ==========
    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        """将 OpenAI 格式消息转换为模型输入"""
        family = self._detect_model_family()
        
        if family == 'qwen':
            return self._build_qwen_prompt(messages)
        elif family == 'hunyuan':
            return self._build_hunyuan_prompt(messages)
        elif family == 'chatglm':
            return self._build_chatglm_prompt(messages)
        else:
            return self._build_chatml_prompt(messages)

    def _build_chatml_prompt(self, messages: List[Dict[str, str]]) -> str:
        """ChatML 格式（通用）"""
        parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def _build_qwen_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Qwen 专用格式（同 ChatML）"""
        return self._build_chatml_prompt(messages)

    def _build_hunyuan_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Hunyuan 格式"""
        # 优先使用 tokenizer 的 chat template
        if self._tokenizer and hasattr(self._tokenizer, 'apply_chat_template'):
            try:
                formatted = self._tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False
                )
                return formatted
            except Exception:
                pass

        # 手动拼接
        parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"Human: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        parts.append("Assistant: ")
        return "\n\n".join(parts)

    def _build_chatglm_prompt(self, messages: List[Dict[str, str]]) -> str:
        """ChatGLM 格式"""
        query_parts = []
        for msg in messages:
            if msg["role"] == "system":
                query_parts.append(f"[System]\n{msg['content']}")
            elif msg["role"] == "user":
                query_parts.append(f"[Question]\n{msg['content']}")
            elif msg["role"] == "assistant":
                query_parts.append(f"[Answer]\n{msg['content']}")
        query_parts.append("[Answer]\n")
        return "\n".join(query_parts)

    # ========== 后处理 ==========
    @staticmethod
    def _extract_hunyuan_answer(text: str) -> str:
        """提取 Hunyuan 模型的回答部分"""
        # 提取 <answer> 标签内容
        answer_match = re.search(r'<answer>\s*(.*?)\s*</answer>', text, re.DOTALL)
        if answer_match:
            return answer_match.group(1).strip()
        
        # 移除 <think> 部分
        if '<think>' in text:
            text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        
        return text.strip()

    def _post_process(self, text: str) -> str:
        """后处理生成的文本"""
        family = self._detect_model_family()
        
        if family == 'hunyuan':
            text = self._extract_hunyuan_answer(text)
        
        # 移除可能的特殊标记
        for marker in ['<|im_end|>', '<|im_start|>', '<|endoftext|>']:
            text = text.replace(marker, '')
        
        return text.strip()

    # ========== 上下文管理 ==========
    def _apply_context_budget(self, prompt: str) -> str:
        """应用上下文预算（截断过长输入）"""
        max_chars = self.config.max_context_chars
        reserved = self.config.reserved_output_chars
        
        if len(prompt) <= max_chars:
            return prompt
        
        # 保留开头和结尾
        keep_start = int(max_chars * 0.7) - reserved
        keep_end = int(max_chars * 0.3)
        
        start = prompt[:keep_start]
        end = prompt[-keep_end:]
        
        return start + "\n... [内容已截断] ...\n" + end

    # ========== 生成接口 ==========
    def chat(self, messages: List[Dict[str, str]], **gen_kwargs) -> str:
        """生成回复"""
        if not messages:
            raise ValueError("消息列表不能为空")

        self._ensure_model_loaded()

        try:
            # 构建 prompt
            prompt = self._build_prompt(messages)
            
            # 应用上下文预算
            prompt = self._apply_context_budget(prompt)
            
            # 合并生成参数
            temperature = gen_kwargs.get("temperature", self.config.temperature)
            max_new_tokens = gen_kwargs.get("max_tokens", self.config.max_tokens)
            top_p = gen_kwargs.get("top_p", self.config.top_p)
            top_k = gen_kwargs.get("top_k", self.config.top_k)
            
            # Tokenize
            inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
            input_length = inputs.input_ids.shape[1]

            # decoder-only 模型不支持 token_type_ids，只保留必要字段
            gen_inputs = {
                "input_ids": inputs["input_ids"],
                "attention_mask": inputs["attention_mask"],
            }

            import torch
            with torch.inference_mode():
                outputs = self._model.generate(
                    **gen_inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature if temperature > 0 else 1.0,
                    do_sample=temperature > 0,
                    top_p=top_p,
                    top_k=top_k,
                    pad_token_id=self._tokenizer.pad_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                    repetition_penalty=self.config.repetition_penalty,
                )
            
            # 解码
            generated_tokens = outputs[0][input_length:]
            response = self._tokenizer.decode(
                generated_tokens,
                skip_special_tokens=True
            ).strip()
            
            # 后处理
            response = self._post_process(response)
            
            # 更新统计
            self._generation_count += 1
            self._total_tokens_generated += len(generated_tokens)
            
            return response
            
        except torch.cuda.OutOfMemoryError:
            cleanup_vram()
            raise OutOfMemoryError(
                "❌ 显存不足 (CUDA Out Of Memory)！请尝试：\n"
                "  1. 缩短输入文本\n"
                "  2. 使用 4-bit 量化 (load_in_4bit=True)\n"
                "  3. 减少 max_tokens"
            )
        except Exception as e:
            cleanup_vram()
            if "out of memory" in str(e).lower():
                raise OutOfMemoryError(f"内存不足: {e}")
            raise GenerationError(f"生成失败: {e}")
        finally:
            cleanup_vram()

    def chat_stream(self, messages: List[Dict[str, str]], **gen_kwargs):
        """流式生成回复：使用 TextIteratorStreamer + 后台线程，逐 token yield"""
        if not messages:
            raise ValueError("消息列表不能为空")

        self._ensure_model_loaded()

        try:
            from transformers import TextIteratorStreamer

            prompt = self._build_prompt(messages)
            prompt = self._apply_context_budget(prompt)

            temperature = gen_kwargs.get("temperature", self.config.temperature)
            max_new_tokens = gen_kwargs.get("max_tokens", self.config.max_tokens)
            top_p = gen_kwargs.get("top_p", self.config.top_p)
            top_k = gen_kwargs.get("top_k", self.config.top_k)

            inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
            gen_inputs = {
                "input_ids": inputs["input_ids"],
                "attention_mask": inputs["attention_mask"],
            }

            streamer = TextIteratorStreamer(
                self._tokenizer,
                skip_prompt=True,
                skip_special_tokens=True,
            )

            gen_error = [None]

            def _run_generate():
                try:
                    import torch
                    with torch.inference_mode():
                        self._model.generate(
                            **gen_inputs,
                            max_new_tokens=max_new_tokens,
                            temperature=temperature if temperature > 0 else 1.0,
                            do_sample=temperature > 0,
                            top_p=top_p,
                            top_k=top_k,
                            pad_token_id=self._tokenizer.pad_token_id,
                            eos_token_id=self._tokenizer.eos_token_id,
                            repetition_penalty=self.config.repetition_penalty,
                            streamer=streamer,
                        )
                except Exception as e:
                    gen_error[0] = e

            t = threading.Thread(target=_run_generate, daemon=True)
            t.start()

            for text in streamer:
                if text:
                    yield text

            t.join()

            if gen_error[0]:
                err = gen_error[0]
                err_msg = str(err).lower()
                if "out of memory" in err_msg:
                    cleanup_vram()
                    raise OutOfMemoryError(f"显存/内存不足: {err}")
                raise GenerationError(f"流式生成失败: {err}")

            self._generation_count += 1

        except Exception:
            cleanup_vram()
            raise
        finally:
            cleanup_vram()

    def warm_up(self):
        """模型预热"""
        if self._model is None:
            self._ensure_model_loaded()
        
        if self._model and 'cuda' in str(self._model.device):
            print("🔥 GPU 模型预热中...")
            self.chat([{"role": "user", "content": "预热测试"}], max_tokens=10)
            print("✅ 模型预热完成")

    def cleanup(self):
        """清理资源"""
        if self._model:
            import torch
            self._model = None
            self._tokenizer = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
            self._load_status = "idle"


# ==================== LLM 管理器（单例优化版） ====================
class LLMManager:
    """单例管理器，支持多任务模型选择（优化版）"""

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

    @property
    def is_configured(self) -> bool:
        """检查是否已配置提供者"""
        return len(self._providers) > 0

    @property
    def tasks(self) -> List[str]:
        """返回所有已配置的任务"""
        with self._provider_lock:
            return list(self._providers.keys())

    def set_provider(self, task: str, provider: LLMProvider):
        """设置提供者"""
        with self._provider_lock:
            # 清理旧提供者
            if task in self._providers:
                old = self._providers[task]
                if hasattr(old, 'cleanup'):
                    try:
                        old.cleanup()
                    except Exception:
                        pass
            
            self._providers[task] = provider

    def get_provider(self, task: str = "default") -> Optional[LLMProvider]:
        """获取提供者（fallback 逻辑）"""
        with self._provider_lock:
            return (
                self._providers.get(task) or 
                self._providers.get("default") or 
                (next(iter(self._providers.values())) if self._providers else None)
            )

    def configure_openai(self, client, model: str, task: str = "default",
                         config: Optional[LLMConfig] = None):
        """配置 OpenAI 提供者"""
        provider = OpenAILLMProvider(client, model, config)
        self.set_provider(task, provider)
        return provider

    def configure_local(self, model_id: str, task: str = "default",
                        load_config: Optional[ModelLoadConfig] = None,
                        llm_config: Optional[LLMConfig] = None):
        """配置本地模型提供者"""
        provider = TransformersLLMProvider(model_id, load_config, llm_config)
        self.set_provider(task, provider)
        return provider

    def chat(self, messages: List[Dict[str, str]], task: str = "default", **gen_kwargs) -> str:
        """统一生成接口"""
        provider = self.get_provider(task)
        if provider is None:
            raise ProviderNotConfiguredError(
                "未配置 LLM 提供者。请先调用 configure_openai() 或 configure_local()"
            )
        
        # 使用带重试的接口
        if "max_retries" in gen_kwargs or "retry_delay" in gen_kwargs:
            return provider.chat_with_retry(messages, **gen_kwargs)
        return provider.chat(messages, **gen_kwargs)

    def chat_stream(self, messages: List[Dict[str, str]], task: str = "default", **gen_kwargs):
        """统一流式生成接口，yield 增量文本片段"""
        provider = self.get_provider(task)
        if provider is None:
            raise ProviderNotConfiguredError(
                "未配置 LLM 提供者。请先调用 configure_openai() 或 configure_local()"
            )
        yield from provider.chat_stream(messages, **gen_kwargs)

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """返回所有任务的状态"""
        with self._provider_lock:
            result = {}
            for task, provider in self._providers.items():
                status_info = {
                    "provider_name": provider.provider_name,
                    "model_name": provider.model_name,
                    "status": provider.status,
                }
                
                # 添加本地模型的额外信息
                if isinstance(provider, TransformersLLMProvider):
                    status_info["load_status"] = provider.load_status
                    status_info["load_error"] = provider.load_error
                    status_info["stats"] = provider.stats
                
                result[task] = status_info
            return result

    def preload_models(self):
        """预加载所有本地模型（后台线程）"""
        with self._provider_lock:
            for task, provider in self._providers.items():
                if isinstance(provider, TransformersLLMProvider):
                    threading.Thread(
                        target=provider._ensure_model_loaded,
                        daemon=True,
                        name=f"model-loader-{task}"
                    ).start()

    def warm_up_all(self):
        """预热所有模型"""
        with self._provider_lock:
            for task, provider in self._providers.items():
                try:
                    provider.warm_up()
                    print(f"✅ 任务 '{task}' 预热完成")
                except Exception as e:
                    print(f"⚠️ 任务 '{task}' 预热失败: {e}")

    def cleanup_all(self):
        """清理所有模型"""
        with self._provider_lock:
            for provider in self._providers.values():
                if hasattr(provider, 'cleanup'):
                    try:
                        provider.cleanup()
                    except Exception:
                        pass
            self._providers.clear()


# ==================== 便捷函数 ====================
def get_llm_manager() -> LLMManager:
    """获取 LLM 管理器单例"""
    return LLMManager()


def create_llm_provider(provider_type: str, **kwargs) -> LLMProvider:
    """工厂函数：创建 LLM 提供者

    Args:
        provider_type: "openai" 或 "local"
        **kwargs: 传递给具体提供者的参数

    Returns:
        LLMProvider 实例
    """
    if provider_type == "openai":
        return OpenAILLMProvider(
            client=kwargs['client'],
            model=kwargs.get('model', 'gpt-3.5-turbo'),
            config=kwargs.get('config')
        )
    elif provider_type == "local":
        return TransformersLLMProvider(
            model_id=kwargs['model_id'],
            load_config=kwargs.get('load_config'),
            llm_config=kwargs.get('llm_config')
        )
    else:
        raise ValueError(f"不支持的提供者类型: {provider_type}")