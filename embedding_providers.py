# embedding_providers.py
"""嵌入提供者抽象层 — 支持 OpenAI API 和 BGE 本地模型"""

import threading
from abc import ABC, abstractmethod
from typing import List, Optional


class EmbeddingProvider(ABC):
    """嵌入提供者抽象基类"""

    @abstractmethod
    def embed(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """为文本列表生成嵌入向量

        Args:
            texts: 输入文本列表
            is_query: True 表示查询文本（BGE 需要加指令前缀），False 表示存储文档

        Returns:
            嵌入向量列表，每个元素为 List[float]
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


# ==================== OpenAI 嵌入提供者 ====================
class OpenAIEmbeddingProvider(EmbeddingProvider):
    """封装 OpenAI Embedding API 调用"""

    def __init__(self, client, model: str):
        """
        Args:
            client: OpenAI 客户端实例
            model: 嵌入模型名称，如 'text-embedding-ada-002'
        """
        self._client = client
        self._model = model

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    def embed(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        # OpenAI 不需要查询前缀，忽略 is_query
        response = self._client.embeddings.create(
            model=self._model,
            input=texts
        )
        return [item.embedding for item in response.data]


# ==================== BGE 本地嵌入提供者 ====================
class BGEEmbeddingProvider(EmbeddingProvider):
    """封装 BAAI BGE 模型本地推理（通过 sentence-transformers）

    模型在首次调用 embed() 时惰性加载，避免阻塞应用启动。
    """

    # BGE 模型推荐的检索查询指令前缀
    QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

    def __init__(self, model_id: str = "BAAI/bge-base-zh-v1.5", device: str = None):
        """
        Args:
            model_id: HuggingFace 模型 ID
            device: 设备，None=自动检测，'cpu'/'cuda'/'cuda:0'
        """
        self._model_id = model_id
        self._device = device
        self._model = None  # 惰性加载
        self._load_error: Optional[str] = None
        self._load_status: str = "idle"  # idle | downloading | loading | ready | error
        self._load_lock = threading.Lock()  # 保护模型加载过程

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

    def _ensure_model_loaded(self):
        """惰性加载模型（首次调用时触发），线程安全的双重检查锁"""
        if self._model is not None:
            return
        with self._load_lock:
            # 双重检查：持锁后再判断一次
            if self._model is not None:
                return
            if self._load_error:
                # 允许重试：清除旧错误状态后重新尝试加载
                err = self._load_error
                self._load_error = None
                self._load_status = "idle"
                # 如果之前是持久性错误（如缺少依赖），这里会再次抛出
                # 但如果是临时错误（如网络问题），则有机会恢复

            self._load_status = "downloading"
            try:
                from sentence_transformers import SentenceTransformer
                self._load_status = "loading"
                self._model = SentenceTransformer(
                    self._model_id,
                    device=self._device
                )
                self._load_status = "ready"
            except ImportError:
                self._load_error = "sentence-transformers 未安装。请运行: pip install sentence-transformers"
                self._load_status = "error"
                raise RuntimeError(self._load_error)
            except Exception as e:
                self._load_error = str(e)
                self._load_status = "error"
                raise RuntimeError(f"无法加载 BGE 模型 '{self._model_id}': {e}")

    def embed(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        self._ensure_model_loaded()

        # BGE 模型：查询侧加指令前缀，文档侧不加
        if is_query:
            texts = [self.QUERY_INSTRUCTION + t for t in texts]

        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,  # L2 归一化，匹配余弦距离
            show_progress_bar=False
        )
        # numpy.ndarray → List[List[float]]
        return embeddings.tolist()


# ==================== 嵌入管理器（单例） ====================
class EmbeddingManager:
    """单例管理器，维护当前活跃的嵌入提供者，线程安全"""

    _instance: Optional["EmbeddingManager"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._provider: Optional[EmbeddingProvider] = None
                    obj._provider_lock = threading.RLock()
                    cls._instance = obj
        return cls._instance

    @property
    def provider(self) -> Optional[EmbeddingProvider]:
        with self._provider_lock:
            return self._provider

    def set_provider(self, provider: EmbeddingProvider):
        with self._provider_lock:
            old = self._provider
            self._provider = provider
        return old

    def configure_openai(self, client, model: str):
        """配置为 OpenAI 嵌入模式"""
        self.set_provider(OpenAIEmbeddingProvider(client, model))

    def configure_bge(self, model_id: str = "BAAI/bge-base-zh-v1.5", device: str = None):
        """配置为 BGE 本地嵌入模式"""
        self.set_provider(BGEEmbeddingProvider(model_id, device))

    def embed(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """委托给当前活跃提供者"""
        with self._provider_lock:
            p = self._provider
        if p is None:
            raise RuntimeError("未配置嵌入提供者，请先配置 API 密钥或选择 BGE 本地模型")
        return p.embed(texts, is_query=is_query)
