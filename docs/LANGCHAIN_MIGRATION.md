# LangChain 迁移指南

本文档记录了翻译工作台从手写架构渐进式迁移到 LangChain LCEL 的完整过程。迁移分 4 个阶段完成，并已移除所有 legacy 兼容代码，LCEL 为唯一路径。

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│  API 层 (FastAPI) — LCEL only                            │
│  /api/translate  /api/epub/replace  /api/kb/hybrid_search│
└──────────────────┬──────────────────────────────────────┘
                   │ LCEL
       ┌───────────▼──────────┐
       │  agents_lcel/         │
       │  ├─ prompts.py        │
       │  ├─ tools.py          │
       │  ├─ chains.py         │
       │  └─ postprocess.py    │
       └───────────┬──────────┘
                   │
       ┌───────────▼──────────┐
       │  langchain_adapters/  │   ← 适配器层
       │  ├─ chat_models.py    │     ChatQoderWork(BaseChatModel)
       │  ├─ embeddings.py     │     QoderWorkEmbeddings(Embeddings)
       │  └─ factory.py        │     get_chat_model() 工厂
       └───────────┬──────────┘
                   │
       ┌───────────▼──────────┐
       │  model_providers.py   │   ← 推理层 (不动)
       │  LLMManager            │     NF4 量化 / 双检锁 / 7 task slot
       │  EmbeddingManager      │     BGE embedding / is_query 区分
       └──────────────────────┘
```

### 检索层

```
┌─────────────────────────────────────────┐
│  services/hybrid_search.py               │
│  → retrievers.HybridRetriever (RRF)      │
└──────────────────┬──────────────────────┘
                   │
       ┌──────────▼──────┐
       │  retrievers/     │
       │  ├─ bm25.py      │
       │  │ BM25Okapi     │
       │  │ + jieba       │
       │  └─ hybrid.py    │
       │    Vector+BM25    │
       │    + RRF(k=60)    │
       │    + CrossEncoder │
       └──────────────────┘
```

## 适配器层详解

### ChatQoderWork (BaseChatModel)

`ChatQoderWork` 是 LangChain `BaseChatModel` 的子类，将 LCEL 链的调用转发到现有的 `LLMManager`，不复制任何推理逻辑。

```python
from langchain_adapters import ChatQoderWork

# 直接构造（不推荐，建议用工厂函数）
chat = ChatQoderWork(task="translate", model_name="qoderwork:translate")

# 同步调用
result = chat.invoke(messages)          # → AIMessage
for chunk in chat.stream(messages):      # → AIMessageChunk (逐 token)
    print(chunk.content, end="")

# 异步调用（内部用 asyncio.to_thread 桥接）
result = await chat.ainvoke(messages)
async for chunk in chat.astream(messages):  # 逐 token yield
    print(chunk.content, end="")
```

**关键实现细节**：

- `_generate()` → `LLMManager().chat()` — 同步调用
- `_stream()` → `LLMManager().chat_stream()` — 逐 chunk yield `ChatGenerationChunk`
- `_agenerate()` → `asyncio.to_thread(_generate)` — 异步桥接
- `_astream()` → daemon thread + Queue + `asyncio.to_thread(q.get)` — 逐 token 异步桥接
- `streaming` 字段**必须为 True**（默认），否则 `_should_stream()` 会跳过流式路径

### QoderWorkEmbeddings (Embeddings)

包装现有 `EmbeddingManager`，保持 BGE 模型的查询前缀区分。

```python
from langchain_adapters import QoderWorkEmbeddings

emb = QoderWorkEmbeddings()
vectors = emb.embed_documents(["text1", "text2"])  # is_query=False
query_vec = emb.embed_query("search query")          # is_query=True
```

### 工厂函数

所有 LCEL 链通过工厂取模型，不直接构造 `ChatQoderWork`。

```python
from langchain_adapters.factory import get_chat_model

# task name 自动映射到 LLMManager slot
chat = get_chat_model(task="paragraph_translate")  # → slot: translate
chat = get_chat_model(task="epub_replace")          # → slot: epub
chat = get_chat_model(task="kb_build")              # → slot: default
```

**Task Slot 映射表**（`_AGENT_TASK_TO_LLM_SLOT`）：

| Agent Task Name | LLMManager Slot |
|---|---|
| `paragraph_translate` | `translate` |
| `long_text_translate` | `translate` |
| `epub_replace` | `epub` |
| `kb_build` | `default` |
| `term_extract` | `default` |

## LCEL Chain 构建

### 使用 chain builder

```python
from agents_lcel.chains import build_chain_for_task, build_translate_runnable

# 通用 chain
chain = build_chain_for_task("paragraph_translate", model_name="qwen2.5-7b-instruct")
result = chain.invoke({"input": "Napoleon conquered Europe."})

# 翻译专用（集成 pre-query 工具结果注入）
chain = build_translate_runnable(
    source_text="The Treaty of Versailles ended WWI.",
    book_title="World History",
    kb_ids=["kb_001"],
    group="history",
    chapter="5",
    use_tm=True,
    use_rag=True,
)
result = chain.invoke({"input": "The Treaty of Versailles ended WWI."})
```

### 工具扩展

在 `agents_lcel/tools.py` 中添加新工具：

```python
from langchain_core.tools import tool

@tool
def my_new_tool(query: str, context: str = "") -> str:
    """工具描述：当 LLM 需要特定信息时调用此工具。"""
    # 实现工具逻辑
    return "tool result"
```

注册到工具列表：

```python
ALL_TRANSLATION_TOOLS = [
    query_terminology,
    query_translation_memory,
    query_knowledge_base,
    my_new_tool,  # 新工具
]
```

**注意**：当前 tool-calling 路径默认关闭（`use_tools=False`），工具结果通过 `prequery_context_for_injection()` 预查询注入 prompt。如需启用真 tool-calling，需同时满足：(1) `use_tools=True` (2) 模型支持 function calling（见 `services/model_capabilities.py`）。

## 混合检索

### BM25 检索器

```python
from retrievers import QoderWorkBM25Retriever

bm25 = QoderWorkBM25Retriever(collection_name="my_kb", k=5)
docs = bm25.invoke("search query")  # → List[Document]
bm25.reload()  # 刷新索引（新增文档后）
```

### HybridRetriever（向量 + BM25 + RRF）

```python
from retrievers import HybridRetriever

hybrid = HybridRetriever(
    collection_name="my_kb",
    k=5,
    semantic_weight=0.6,
    keyword_weight=0.4,
    use_reranker=False,  # 开启 CrossEncoder rerank
)
docs = hybrid.invoke("search query")  # → List[Document]
```

## 可观测性

LCEL 链自动挂载 `QoderWorkCallbackHandler`，所有事件（chain/LLM/tool/retriever 的 start/end/error）写入 `logs/langchain.log`。

```
2026-06-22 10:30:15 | INFO    | CHAIN_START  [RunnableSequence] run=a1b2c3d4 input={"input": "Napoleon..."}
2026-06-22 10:30:15 | INFO    | LLM_START    [ChatQoderWork] run=e5f6g7h8 msgs=2
2026-06-22 10:30:16 | INFO    | LLM_END      run=e5f6g7h8 output=拿破仑征服了欧洲。
2026-06-22 10:30:16 | INFO    | CHAIN_END    run=a1b2c3d4 output=拿破仑征服了欧洲。
```

**配置**：

```python
from observability import setup_langchain_logging

# 自定义日志目录和轮转参数
setup_langchain_logging(
    log_dir="/path/to/logs",
    max_bytes=10 * 1024 * 1024,  # 10MB
    backup_count=5,
    level=logging.DEBUG,  # 开启逐 token 日志
)
```

默认行为：5MB 轮转，保留 3 个备份，INFO 级别。

## 环境变量开关

迁移完成后，`USE_LANGCHAIN` 和 `BM25_BACKEND` 环境变量开关已移除。所有 API 端点和混合检索均直接使用 LCEL / HybridRetriever 路径，无需手动切换。

## 已知陷阱与解决方案

### `streaming` 字段陷阱

`BaseChatModel._should_stream()` 检查 `_streaming_disabled()`。如果工厂创建 `ChatQoderWork` 时显式传 `streaming=False`，`streaming` 进入 `model_fields_set`，`_streaming_disabled()` 返回 True，导致 `chain.astream()` 退化为单次 `ainvoke()`。

**解决**：工厂 `streaming` 参数默认值为 `True`。

### `_astream` 只返回 1 个 chunk

LangChain 基类默认的 `_astream` 把整个 `_stream` generator 跑完再一次性 yield。

**解决**：自定义 `_astream` 用 daemon thread + Queue + `asyncio.to_thread(q.get)` 桥接。

### BM25Okapi IDF=0

标准 BM25 公式 `IDF = log((N-n+0.5)/(n+0.5))` 在 N=2n 时给出 IDF=0。

**解决**：`_smooth_idf()` 重算：`log((N+1)/(n+1)) + 1.0`，下限 0.1。

### `@tool` 不可 mock patch

`@tool` 装饰器生成 `StructuredTool`（Pydantic model），其 `.invoke` 不是普通属性，`unittest.mock.patch` 会失败。

**解决**：测试时 mock `prequery_context_for_injection()` 而非单个 tool 的 `.invoke()`。

### `ainvoke` 路由变化

`streaming=True` 时，LangChain 基类的 `ainvoke()` 会走 `_astream` → `chat_stream()` 路径（而非 `_agenerate` → `chat()`）。

**注意**：确保 `chat_stream` 和 `chat` 返回语义一致的结果。

## 新增依赖 (Phase 1-4)

```
langchain-core>=0.3.0,<1.0.0
langchain>=0.3.0,<1.0.0
langchain-community>=0.3.0,<1.0.0
langchain-chroma>=0.2.0,<1.0.0
langchain-huggingface>=0.1.0,<1.0.0
langchain-openai>=0.2.0,<1.0.0
rank-bm25>=0.2.2,<1.0.0
jieba>=0.42.1
```

## 目录结构（新增文件）

```
backend/
├── langchain_adapters/          # Phase 1: LangChain 适配器
│   ├── __init__.py
│   ├── chat_models.py           # ChatQoderWork(BaseChatModel)
│   ├── embeddings.py            # QoderWorkEmbeddings(Embeddings)
│   └── factory.py               # get_chat_model() / get_embeddings()
│
├── agents_lcel/                 # Phase 2: LCEL Agent chains
│   ├── __init__.py
│   ├── prompts.py               # ChatPromptTemplate × 4
│   ├── tools.py                 # @tool × 3
│   ├── chains.py                # build_chain_for_task() / build_translate_runnable()
│   └── postprocess.py           # clean_translation / clean_epub / get_cleaner
│
├── retrievers/                  # Phase 3: 混合检索
│   ├── __init__.py
│   ├── bm25.py                  # QoderWorkBM25Retriever (BM25Okapi + jieba)
│   └── hybrid.py                # HybridRetriever (Vector + BM25 + RRF)
│
├── observability/               # Phase 4: 可观测性
│   ├── __init__.py
│   └── callbacks.py             # QoderWorkCallbackHandler → logs/langchain.log
│
├── services/
│   ├── model_capabilities.py    # Phase 2: supports_tool_calling() 查表
│   └── hybrid_search.py         # Phase 3: HybridRetriever (RRF fusion)
│
├── tests/                       # Phase 4: 回归测试
│   └── test_regression.py       # 7 项回归测试
│
└── ...

logs/                            # LangChain 事件日志 (自动创建)
└── langchain.log

docs/
└── LANGCHAIN_MIGRATION.md       # 本文档
```
