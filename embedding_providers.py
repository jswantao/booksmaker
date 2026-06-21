# embedding_providers.py
"""嵌入提供者抽象层 — 支持 OpenAI API 和 BGE 本地模型（优化版）"""

import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Callable, Tuple

from utils.cuda import cleanup_vram


# ==================== 异常定义 ====================
class EmbeddingError(Exception):
    """嵌入处理异常"""
    pass


class ModelLoadError(EmbeddingError):
    """模型加载异常"""
    pass


class ProviderNotConfiguredError(EmbeddingError):
    """提供者未配置异常"""
    pass


# ==================== 数据类 ====================
@dataclass
class EmbeddingConfig:
    """嵌入配置"""
    batch_size: int = 16
    max_text_length: int = 512
    normalize: bool = True
    cache_enabled: bool = True
    cache_size: int = 1000


# ==================== 抽象基类 ====================
class EmbeddingProvider(ABC):
    """嵌入提供者抽象基类"""

    def __init__(self, config: Optional[EmbeddingConfig] = None):
        self.config = config or EmbeddingConfig()

    @abstractmethod
    def embed(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """为文本列表生成嵌入向量

        Args:
            texts: 输入文本列表
            is_query: True 表示查询文本，False 表示存储文档

        Returns:
            嵌入向量列表，每个元素为 List[float]
        """
        ...

    def embed_batch(self, texts: List[str], is_query: bool = False,
                    progress_callback: Optional[Callable[[int, int], None]] = None) -> List[List[float]]:
        """分批处理大量文本

        Args:
            texts: 输入文本列表
            is_query: 是否为查询文本
            progress_callback: 进度回调 (current, total)

        Returns:
            所有文本的嵌入向量列表
        """
        all_embeddings = []
        total = len(texts)
        batch_size = self.config.batch_size

        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            try:
                embeddings = self.embed(batch, is_query=is_query)
                all_embeddings.extend(embeddings)

                if progress_callback:
                    progress_callback(min(i + batch_size, total), total)
            except Exception as e:
                raise EmbeddingError(f"批次 {i // batch_size} 处理失败: {e}")

        return all_embeddings

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
    def dimension(self) -> Optional[int]:
        """嵌入维度（子类可重写）"""
        return None

    def warm_up(self):
        """模型预热（子类可重写）"""
        pass

    def cleanup(self):
        """资源清理（子类可重写）"""
        pass


# ==================== OpenAI 嵌入提供者 ====================
class OpenAIEmbeddingProvider(EmbeddingProvider):
    """封装 OpenAI Embedding API 调用（优化版）"""

    # OpenAI 嵌入模型维度映射
    DIMENSION_MAP = {
        "text-embedding-ada-002": 1536,
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
    }

    # OpenAI API 限制
    MAX_BATCH_SIZE = 2048
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

    def __init__(self, client, model: str, config: Optional[EmbeddingConfig] = None):
        """
        Args:
            client: OpenAI 客户端实例
            model: 嵌入模型名称
            config: 嵌入配置
        """
        super().__init__(config)
        self._client = client
        self._model = model
        self._validate_batch_size()

    def _validate_batch_size(self):
        """验证批处理大小"""
        if self.config.batch_size > self.MAX_BATCH_SIZE:
            self.config.batch_size = self.MAX_BATCH_SIZE

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> Optional[int]:
        return self.DIMENSION_MAP.get(self._model)

    def embed(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        if not texts:
            return []

        # 限制单次请求的文本数量
        if len(texts) > self.MAX_BATCH_SIZE:
            return self.embed_batch(texts, is_query)

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=texts
                )
                return [item.embedding for item in response.data]

            except Exception as e:
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY * (2 ** attempt))  # 指数退避
                    continue
                raise EmbeddingError(f"OpenAI 嵌入失败 (重试 {self.MAX_RETRIES} 次): {e}")

    def warm_up(self):
        """预热：发送一个简单的请求测试连接"""
        try:
            self.embed(["warm up"])
        except Exception:
            pass


# ==================== BGE 本地嵌入提供者 ====================
class BGEEmbeddingProvider(EmbeddingProvider):
    """封装 BAAI BGE 模型本地推理（优化版）

    优先使用 ModelScope 下载，失败时回退到 Hugging Face。
    支持模型预热、缓存和动态批处理。
    """

    # BGE 模型推荐的检索查询指令前缀
    QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

    # Hugging Face ID → ModelScope ID 映射表
    MODEL_MAPPING = {
        "BAAI/bge-small-zh": "AI-ModelScope/bge-small-zh",
        "BAAI/bge-base-zh-v1.5": "AI-ModelScope/bge-base-zh-v1.5",
        "BAAI/bge-large-zh": "AI-ModelScope/bge-large-zh",
        "BAAI/bge-small-en": "AI-ModelScope/bge-small-en",
        "BAAI/bge-base-en": "AI-ModelScope/bge-base-en",
        "BAAI/bge-large-en": "AI-ModelScope/bge-large-en",
    }

    # 模型维度映射
    DIMENSION_MAP = {
        "BAAI/bge-small-zh": 512,
        "BAAI/bge-base-zh-v1.5": 768,
        "BAAI/bge-large-zh": 1024,
        "BAAI/bge-small-en": 384,
        "BAAI/bge-base-en": 768,
        "BAAI/bge-large-en": 1024,
    }

    def __init__(self, model_id: str = "BAAI/bge-base-zh-v1.5", device: str = None,
                 cache_dir: str = "./models", download_source: str = "huggingface",
                 config: Optional[EmbeddingConfig] = None):
        """
        Args:
            model_id: 模型 ID（Hugging Face 格式）
            device: 设备，None=自动检测，'cpu'/'cuda'/'cuda:0'
            cache_dir: 模型缓存根目录
            download_source: 下载源 "huggingface" | "modelscope"
            config: 嵌入配置
        """
        super().__init__(config)
        self._model_id = model_id
        self._device = device
        self._cache_dir = cache_dir
        self._download_source = download_source
        self._model = None
        self._model_path: Optional[str] = None
        self._load_error: Optional[str] = None
        self._load_status: str = "idle"
        self._load_lock = threading.Lock()
        self._source: str = "unknown"
        self._max_seq_length: Optional[int] = None

    @property
    def provider_name(self) -> str:
        return "bge"

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
    def source(self) -> str:
        """模型来源：modelscope / huggingface / local"""
        return self._source

    @property
    def dimension(self) -> Optional[int]:
        return self.DIMENSION_MAP.get(self._model_id)

    def _get_modelscope_id(self, hf_id: str) -> Optional[str]:
        """将 Hugging Face ID 转换为 ModelScope ID"""
        return self.MODEL_MAPPING.get(hf_id)

    def _get_safe_max_length(self) -> int:
        """获取安全的文本最大长度"""
        if self._max_seq_length is not None:
            return self._max_seq_length

        # BGE 模型默认 max_position_embeddings 为 512
        if self._model and hasattr(self._model, 'max_seq_length'):
            self._max_seq_length = self._model.max_seq_length
        else:
            self._max_seq_length = 512

        return self._max_seq_length

    def _truncate_texts(self, texts: List[str]) -> List[str]:
        """智能截断文本（基于模型最大长度）"""
        max_length = self._get_safe_max_length()
        # 粗略估算：中文约1.5字符/token，英文约4字符/token
        char_limit = max_length * 3  # 保守估计

        truncated = []
        for text in texts:
            if len(text) > char_limit:
                # 保留前 max_length*2 字符（大致对应 max_length tokens）
                truncated.append(text[:max_length * 2])
            else:
                truncated.append(text)

        return truncated

    def _download_from_modelscope(self, model_id: str) -> Optional[str]:
        """使用 ModelScope 下载模型，返回本地路径"""
        try:
            from modelscope import snapshot_download
        except ImportError:
            self._load_error = "modelscope 未安装。请运行: pip install modelscope"
            return None

        try:
            modelscope_id = self._get_modelscope_id(model_id)
            if modelscope_id is None:
                self._load_error = f"ModelScope 未同步模型 '{model_id}'，请检查映射表"
                return None

            self._load_status = "downloading"
            print(f"📥 [ModelScope] 正在下载模型: {modelscope_id}")

            model_path = snapshot_download(
                modelscope_id,
                cache_dir=self._cache_dir,
                revision="master",
                ignore_file_pattern=[r".*\.h5", r".*\.ot", r".*\.pb", r".*\.msgpack"]
            )
            print(f"✅ [ModelScope] 模型下载完成: {model_path}")
            self._source = "modelscope"
            return model_path
        except Exception as e:
            self._load_error = f"ModelScope 下载失败: {e}"
            print(f"⚠️ {self._load_error}")
            return None

    def _download_from_huggingface(self, model_id: str) -> Optional[str]:
        """使用 Hugging Face 下载模型，返回本地路径"""
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            self._load_error = "huggingface-hub 未安装。请运行: pip install huggingface-hub"
            return None

        try:
            self._load_status = "downloading"
            print(f"📥 [Hugging Face] 正在下载模型: {model_id}")

            # 尝试使用镜像站
            endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
            model_path = snapshot_download(
                repo_id=model_id,
                cache_dir=self._cache_dir,
                local_dir_use_symlinks=False,
                resume_download=True,
                endpoint=endpoint,
                ignore_patterns=["*.h5", "*.ot", "*.pb", "*.msgpack"]
            )
            print(f"✅ [Hugging Face] 模型下载完成: {model_path}")
            self._source = "huggingface"
            return model_path
        except Exception as e:
            self._load_error = f"Hugging Face 下载失败: {e}"
            print(f"⚠️ {self._load_error}")
            return None

    def _find_local_model(self, model_id: str) -> Optional[str]:
        """检查本地缓存中是否已有模型（增强版）"""
        # 检查路径列表
        check_paths = []

        # 1. ModelScope 格式路径
        modelscope_id = self._get_modelscope_id(model_id)
        if modelscope_id:
            check_paths.append(("local_modelscope", os.path.join(self._cache_dir, modelscope_id)))

        # 2. Hugging Face 格式路径
        hf_cache_name = f"models--{model_id.replace('/', '--')}"
        hf_cache_root = os.path.join(self._cache_dir, hf_cache_name)
        if os.path.exists(hf_cache_root):
            snapshots_dir = os.path.join(hf_cache_root, "snapshots")
            if os.path.exists(snapshots_dir):
                for snapshot_id in sorted(os.listdir(snapshots_dir), reverse=True):
                    check_paths.append(("local_huggingface", os.path.join(snapshots_dir, snapshot_id)))

        # 3. 简单路径
        check_paths.append(("local_simple", os.path.join(self._cache_dir, model_id.split('/')[-1])))

        # 4. 用户自定义路径
        custom_path = os.environ.get("BGE_MODEL_PATH")
        if custom_path and os.path.exists(custom_path):
            check_paths.append(("local_custom", custom_path))

        # 检查所有路径
        required_files = ["config.json"]  # 至少需要配置文件
        for source_name, path in check_paths:
            if os.path.exists(path) and os.path.isdir(path):
                # 检查是否有必要的模型文件
                model_files = ["pytorch_model.bin", "model.safetensors", "tf_model.h5"]
                has_model = any(os.path.exists(os.path.join(path, f)) for f in model_files)
                has_config = os.path.exists(os.path.join(path, "config.json"))

                if has_config:  # 至少有配置文件（可能从HF在线加载权重）
                    print(f"✅ [本地缓存] 找到模型 ({source_name}): {path}")
                    self._source = source_name
                    return path

        return None

    def _ensure_model_loaded(self):
        """惰性加载模型（优化版）"""
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
                import torch
                from sentence_transformers import SentenceTransformer

                # 确定设备
                if self._device is None or self._device == "auto":
                    target_device = "cuda:0" if torch.cuda.is_available() else "cpu"
                else:
                    target_device = self._device

                print(f"🎯 目标设备: {target_device}")

                # 1. 优先检查本地缓存
                local_path = self._find_local_model(self._model_id)
                if local_path:
                    self._load_model_from_path(local_path, target_device)
                    return

                # 2. 根据下载源选择下载通道
                model_path = None
                if self._download_source == "modelscope":
                    model_path = self._download_from_modelscope(self._model_id)
                    if not model_path:
                        print("⚠️ ModelScope 下载失败，回退到 HuggingFace...")
                        model_path = self._download_from_huggingface(self._model_id)
                else:
                    model_path = self._download_from_huggingface(self._model_id)

                if model_path:
                    self._load_model_from_path(model_path, target_device)
                    return

                # 所有方式都失败
                self._load_status = "error"
                raise ModelLoadError(f"无法加载 BGE 模型 '{self._model_id}': {self._load_error}")

            except ImportError as e:
                error_msg = str(e)
                if "sentence-transformers" in error_msg:
                    self._load_error = "sentence-transformers 未安装。请运行: pip install sentence-transformers"
                else:
                    self._load_error = error_msg
                self._load_status = "error"
                raise ModelLoadError(self._load_error)
            except ModelLoadError:
                raise
            except Exception as e:
                self._load_error = str(e)
                self._load_status = "error"
                raise ModelLoadError(f"无法加载 BGE 模型 '{self._model_id}': {e}")

    def _load_model_from_path(self, model_path: str, target_device: str):
        """从路径加载模型"""
        from sentence_transformers import SentenceTransformer

        self._load_status = "loading"
        print(f"🔄 正在加载模型: {model_path}")

        self._model = SentenceTransformer(
            model_path,
            device=target_device,
            cache_folder=self._cache_dir
        )
        self._model_path = model_path

        # 获取模型最大序列长度
        if hasattr(self._model, 'max_seq_length'):
            self._max_seq_length = self._model.max_seq_length
        elif hasattr(self._model, '_first_module') and hasattr(self._model._first_module(), 'max_seq_length'):
            self._max_seq_length = self._model._first_module().max_seq_length

        self._load_status = "ready"
        print(f"✅ BGE 模型加载成功 (来源: {self._source}, 设备: {target_device}, "
              f"最大长度: {self._max_seq_length})")

    def embed(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """生成嵌入向量（优化版）"""
        if not texts:
            return []

        self._ensure_model_loaded()

        try:
            # 智能截断文本（基于模型最大长度）
            safe_texts = self._truncate_texts(texts)

            # BGE 模型：查询侧加指令前缀，文档侧不加
            if is_query:
                safe_texts = [self.QUERY_INSTRUCTION + t for t in safe_texts]

            import torch
            with torch.inference_mode():
                embeddings = self._model.encode(
                    safe_texts,
                    normalize_embeddings=self.config.normalize,
                    batch_size=self.config.batch_size,
                    show_progress_bar=False,
                    convert_to_numpy=True
                )

            return embeddings.tolist()
        except Exception as e:
            raise EmbeddingError(f"BGE 嵌入生成失败: {e}")
        finally:
            cleanup_vram()

    def warm_up(self):
        """模型预热：加载模型并运行一次推理"""
        if self._model is None:
            self._ensure_model_loaded()

        if self._model and self._device and 'cuda' in str(self._device):
            print("🔥 GPU 模型预热中...")
            self.embed(["模型预热测试文本"], is_query=False)
            print("✅ 模型预热完成")

    def cleanup(self):
        """清理模型资源"""
        if self._model:
            import torch
            import gc

            self._model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()


# ==================== 嵌入管理器（单例优化版） ====================
class EmbeddingManager:
    """单例管理器，维护当前活跃的嵌入提供者（优化版）"""

    _instance: Optional["EmbeddingManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._provider: Optional[EmbeddingProvider] = None
                    obj._provider_lock = threading.RLock()
                    obj._embed_cache: dict = {}
                    obj._cache_enabled = True
                    cls._instance = obj
        return cls._instance

    @property
    def provider(self) -> Optional[EmbeddingProvider]:
        with self._provider_lock:
            return self._provider

    @property
    def is_configured(self) -> bool:
        """检查是否已配置提供者"""
        return self.provider is not None

    def set_provider(self, provider: EmbeddingProvider):
        """设置嵌入提供者"""
        with self._provider_lock:
            old = self._provider

            # 清理旧提供者
            if old and hasattr(old, 'cleanup'):
                try:
                    old.cleanup()
                except Exception:
                    pass

            self._provider = provider
            self._clear_cache()

        return old

    def configure_openai(self, client, model: str, config: Optional[EmbeddingConfig] = None):
        """配置为 OpenAI 嵌入模式"""
        provider = OpenAIEmbeddingProvider(client, model, config)
        self.set_provider(provider)
        return provider

    def configure_bge(self, model_id: str = "BAAI/bge-base-zh-v1.5", device: str = None,
                      cache_dir: str = "./models", download_source: str = "huggingface",
                      config: Optional[EmbeddingConfig] = None):
        """配置为 BGE 本地嵌入模式"""
        provider = BGEEmbeddingProvider(model_id, device, cache_dir, download_source, config)
        self.set_provider(provider)
        return provider

    def embed(self, texts: List[str], is_query: bool = False, use_cache: bool = False) -> List[List[float]]:
        """委托给当前活跃提供者（支持缓存）

        Args:
            texts: 输入文本列表
            is_query: 是否为查询文本
            use_cache: 是否使用缓存（仅对非查询文本有效）

        Returns:
            嵌入向量列表
        """
        provider = self.provider
        if provider is None:
            raise ProviderNotConfiguredError("未配置嵌入提供者，请先配置 API 密钥或选择 BGE 本地模型")

        if use_cache and not is_query and self._cache_enabled:
            return self._embed_with_cache(provider, texts)

        return provider.embed(texts, is_query=is_query)

    def embed_batch(self, texts: List[str], is_query: bool = False,
                    progress_callback: Optional[Callable[[int, int], None]] = None) -> List[List[float]]:
        """批量嵌入（支持进度回调）"""
        provider = self.provider
        if provider is None:
            raise ProviderNotConfiguredError("未配置嵌入提供者")

        return provider.embed_batch(texts, is_query, progress_callback)

    def _embed_with_cache(self, provider: EmbeddingProvider, texts: List[str]) -> List[List[float]]:
        """带缓存的嵌入生成"""
        results = []
        uncached_texts = []
        uncached_indices = []

        # 查找缓存
        for i, text in enumerate(texts):
            if text in self._embed_cache:
                results.append((i, self._embed_cache[text]))
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
                results.append((i, None))

        # 生成未缓存的嵌入
        if uncached_texts:
            new_embeddings = provider.embed(uncached_texts, is_query=False)

            # 更新缓存
            for text, embedding in zip(uncached_texts, new_embeddings):
                self._embed_cache[text] = embedding

            # 填充结果
            for idx, embedding in zip(uncached_indices, new_embeddings):
                results[idx] = (idx, embedding)

        # 按原顺序返回
        return [emb for _, emb in sorted(results, key=lambda x: x[0])]

    def _clear_cache(self):
        """清空缓存"""
        self._embed_cache.clear()

    def set_cache_enabled(self, enabled: bool):
        """启用/禁用缓存"""
        self._cache_enabled = enabled
        if not enabled:
            self._clear_cache()

    def warm_up(self):
        """预热当前提供者"""
        provider = self.provider
        if provider:
            provider.warm_up()

    def cleanup(self):
        """清理资源"""
        with self._provider_lock:
            if self._provider and hasattr(self._provider, 'cleanup'):
                self._provider.cleanup()
            self._clear_cache()


# ==================== 便捷函数 ====================
def get_embedding_manager() -> EmbeddingManager:
    """获取嵌入管理器单例"""
    return EmbeddingManager()


def create_embedding_provider(provider_type: str, **kwargs) -> EmbeddingProvider:
    """工厂函数：创建嵌入提供者

    Args:
        provider_type: "openai" 或 "bge"
        **kwargs: 传递给具体提供者的参数

    Returns:
        EmbeddingProvider 实例
    """
    if provider_type == "openai":
        return OpenAIEmbeddingProvider(
            client=kwargs.get('client'),
            model=kwargs.get('model', 'text-embedding-ada-002'),
            config=kwargs.get('config')
        )
    elif provider_type == "bge":
        return BGEEmbeddingProvider(
            model_id=kwargs.get('model_id', 'BAAI/bge-base-zh-v1.5'),
            device=kwargs.get('device'),
            cache_dir=kwargs.get('cache_dir', './models'),
            download_source=kwargs.get('download_source', 'huggingface'),
            config=kwargs.get('config')
        )
    else:
        raise ValueError(f"不支持的提供者类型: {provider_type}")