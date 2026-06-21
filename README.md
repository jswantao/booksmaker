# 智能翻译与EPUB工作台 (Smart Translation & EPUB Workbench)

本地历史学术翻译系统 —— 知识库 + 记忆库双轨设计，支持离线批量翻译和 EPUB 电子书生成。

## 快速启动

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. (可选) 设置 ModelScope 下载源（国内加速）
set HF_ENDPOINT=https://hf-mirror.com
set MODELSCOPE_CACHE_DIR=G:\huggingface_cache

# 3. 启动服务
python app.py
# 访问 http://localhost:8008
```

启动后，在配置面板选择「本地模型 (Qwen2-7B-Instruct)」→「保存并测试」，首次会下载模型。

## 项目结构

```
├── app.py                           # FastAPI 入口
├── config.py                        # 全局配置与环境变量
├── agents.py                        # Agent 定义（世界史专家 + EPUB 编辑）
├── model_providers.py               # LLM 抽象层 (OpenAI + 本地 Transformers)
├── embedding_providers.py           # 嵌入抽象层 (OpenAI + BGE 本地)
├── requirements.txt                 # Python 依赖
│
├── api/                             # API 路由层
│   ├── __init__.py                  # 路由聚合
│   ├── config.py                    # 配置端点
│   ├── translate.py                 # 单句翻译端点
│   ├── epub.py                      # EPUB 生成/替换端点
│   ├── tm.py                        # 翻译记忆库 CRUD
│   ├── knowledge.py                 # 知识库/分组/混合检索
│   └── pipeline.py                  # 翻译流水线 API
│
├── core/                            # 核心基础设施
│   ├── database.py                  # ChromaDB 持久化客户端
│   └── dependencies.py              # OpenAI 客户端工厂 + LLM 同步
│
├── models/                          # 数据模型
│   ├── schemas.py                   # Pydantic 请求/响应模型
│   └── agent.py                     # Agent 数据模型
│
├── services/                        # 业务服务层
│   ├── translation_memory.py        # TM: SQLite + ChromaDB 双存
│   ├── knowledge_manager.py         # KB 元数据管理 (SQLite)
│   ├── knowledge_service.py         # RAG 操作 (添加/查询/多KB)
│   ├── embedding_service.py         # 嵌入提供者同步
│   ├── epub_service.py              # EPUB 文件生成 (ebooklib)
│   ├── document_processor.py        # 文档预处理 (章节切分 + 术语提取)
│   ├── hybrid_search.py             # 混合检索 (向量 + 关键词)
│   ├── memory_bank.py               # JSON 记忆库 (术语/摘要/进度)
│   ├── translate_optimizer.py       # 翻译增强 (术语表/后处理/评论截断)
│   └── translation_pipeline.py      # 翻译流水线编排
│
├── templates/
│   └── index.html                   # 前端 SPA (三标签页)
│
├── static/
│   ├── app.js                       # 前端入口
│   ├── api.js                       # HTTP API 通信层
│   ├── config.js                    # 常量定义
│   ├── dom.js                       # DOM 缓存 + 事件委托
│   ├── state.js                     # 全局应用状态
│   ├── ui.js                        # 渲染函数
│   ├── utils.js                     # 工具函数
│   └── modules/
│       ├── config-panel.js          # API 配置面板
│       ├── translator.js            # 翻译/EPUB 提交
│       ├── kb-manager.js            # 知识库管理
│       ├── tm-manager.js            # 翻译记忆库管理
│       ├── pipeline.js              # 翻译流水线面板
│       └── theme.js                 # 暗色/亮色主题
│
├── chroma_db/                       # ChromaDB 向量库 (自动创建)
├── uploads/                         # 文件上传目录
├── memory/                          # 记忆库 JSON 文件
├── translation_memory.db            # SQLite 翻译记忆库
└── kb_manager.db                    # SQLite 知识库元数据
```

## 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | API 服务和静态文件 |
| LLM | Qwen2-7B-Instruct (bitsandbytes 4-bit NF4) | 本地翻译推理 (~4-5GB 显存) |
| 嵌入 | BAAI/bge-base-zh-v1.5 (CPU) | 本地语义向量 |
| 向量库 | ChromaDB | RAG 知识库 + 翻译记忆向量检索 |
| 记忆库 | JSON (原子写入 + 自动备份) | 术语公约 + 进度持久化 |
| 翻译记忆 | SQLite + ChromaDB 双存 | 精确匹配 + 向量相似度 |
| 量化 | bitsandbytes 4-bit NF4 | 降低显存占用 |
| 下载 | HuggingFace / ModelScope 魔搭社区 | 模型下载（国内加速） |
| EPUB | ebooklib | 电子书文件生成 |
| 前端 | 原生 HTML/CSS/JS (ES Module) | SPA 三标签页 |

## 架构总览

```
[离线预处理]
  历史专著(PDF/TXT) → 按章切分 → 术语提取 → 构建知识库(ChromaDB)

[单句翻译] (翻译工作台标签页)
  用户输入 → TM精确匹配 → TM模糊匹配 → RAG混合检索 → LLM翻译 → 后处理 → 存入TM

[分段翻译循环] (翻译流水线标签页)
  Chunk N → KB混合检索(Top-2) → 记忆库上下文 → 模型翻译
  → 评论截断 + 术语替换 → 更新记忆库 → 清理显存
  → 每10段自动保存 → 章节缝合 → 输出终稿 final_output.md

[章节缝合]
  合并译文 → 术语一致性报告 → 引用补全 → 输出 Markdown 终稿
```

### 双轨设计

| 轨道 | 存储 | 内容 | 用途 |
|------|------|------|------|
| **知识库 (KB)** | ChromaDB 向量库 | 历史专著按章切分片段 | 翻译时检索 Top-2 最相关上下文 |
| **记忆库 (Memory)** | JSON 文件 | 术语公约 + 段落摘要 + 核心论点 + 进度 | 跨片段保持术语一致性 + 断点续译 |

### 模型选型

| 模型 | 格式 | 显存 | 用途 |
|------|------|------|------|
| Qwen2-7B-Instruct | bitsandbytes 4-bit NF4 | ~4-5GB | 翻译推理 |
| BAAI/bge-base-zh-v1.5 | FP32 (CPU) | ~400MB 内存 | 语义嵌入 |

### LLM 提供者架构

```
LLMManager (单例，per-task 模型，线程安全)
├── OpenAILLMProvider           # 远程 API (GPT-4 等)
└── TransformersLLMProvider     # 本地模型
        ├── 4-bit: bitsandbytes BitsAndBytesConfig (load_in_4bit, NF4)
        ├── 8-bit: load_in_8bit
        ├── FP16: float16 全精度
        ├── 下载: HuggingFace Hub / ModelScope SDK
        └── 惰性加载 + 线程安全双检锁
```

### 嵌入提供者架构

```
EmbeddingManager (单例，线程安全切换)
├── OpenAIEmbeddingProvider     # 远程 API
└── BGEEmbeddingProvider        # 本地 BGE 模型
        ├── 下载策略: ModelScope 优先 → HuggingFace 回退
        ├── 本地缓存检测 (modelscope / huggingface / simple)
        ├── 查询自动添加 BGE 指令前缀
        └── L2 归一化输出
```

## 三个功能标签页

### 1. 翻译工作台 📝
- 单段英文历史文本 → 中文翻译
- 翻译记忆库 (TM) 增强 + RAG 知识库检索
- 混合检索（向量语义 + 全文关键词，加权重排序）
- EPUB 电子书代码生成与内容替换

### 2. 知识库管理 📚
- 知识库 CRUD（创建/编辑/删除）
- 分组管理
- Agent-KB 分配（为不同智能体绑定默认知识库）
- 文档上传（TXT/PDF）
- KB 选择器（翻译/EPUB 面板各自选择）

### 3. 翻译流水线 📋
- **步骤1**: 上传历史专著 (TXT/PDF)
- **步骤2**: 构建知识库 (按章切分 → 嵌入 → ChromaDB)
- **步骤3**: 启动翻译流水线 (分段翻译 → 记忆库 → 自动保存)
- **步骤4**: 章节缝合 (合并译文 → 术语报告 → 终稿)
- 实时进度轮询 + 暂停/恢复 + 断点续译

## API 端点

### 配置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/config` | 获取/保存 API 配置 |
| GET | `/api/config/embedding/status` | BGE 加载状态 |
| GET | `/api/config/llm/status` | LLM 加载状态 |
| POST | `/api/config/embedding` | 切换嵌入提供者 |

### 翻译
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/translate` | 单句翻译（TM + RAG + 后处理） |
| POST | `/api/generate_epub` | 生成 EPUB 代码 |
| POST | `/api/replace_epub` | 替换 EPUB 内容 |
| GET | `/api/download/epub/{filename}` | 下载 EPUB 文件 |

### 翻译记忆库 (TM)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tm` | 获取记忆列表 |
| POST | `/api/tm/search` | 搜索记忆 |
| POST | `/api/tm` | 手动添加翻译对 |
| DELETE | `/api/tm/{id}` | 删除单条 |
| DELETE | `/api/tm/clear` | 清空记忆库 |
| POST | `/api/tm/reindex` | 重建向量索引 |

### 知识库 (KB)
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/kb` | 获取/创建知识库 |
| PUT/DELETE | `/api/kb/{id}` | 更新/删除知识库 |
| POST | `/api/kb/{id}/upload` | 上传文档到知识库 |
| GET/POST | `/api/kb/groups` | 获取/创建分组 |
| PUT/DELETE | `/api/kb/groups/{id}` | 更新/删除分组 |
| POST | `/api/knowledge/upload` | 上传知识文档 |
| GET | `/api/knowledge` | 知识库状态摘要 |

### 翻译流水线 (Pipeline)
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/pipeline/upload` | 上传文档 (TXT/PDF) |
| POST | `/api/pipeline/build-kb` | 构建知识库 |
| POST | `/api/pipeline/run` | 启动翻译流水线 |
| POST | `/api/pipeline/pause/{kb_name}` | 暂停流水线 |
| POST | `/api/pipeline/resume/{kb_name}` | 恢复流水线 |
| GET | `/api/pipeline/status/{kb_name}` | 查询进度 |
| GET | `/api/pipeline/result/{kb_name}` | 获取翻译结果 |
| POST | `/api/pipeline/stitch` | 章节缝合 |
| GET | `/api/pipeline/kbs` | 列出可用知识库 |
| POST | `/api/pipeline/memory/init` | 初始化记忆库 |
| GET | `/api/pipeline/memory/{path}` | 查询记忆库状态 |

## 配置

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `openai` | LLM 提供者: `openai` 或 `local` |
| `LOCAL_TRANSLATE_MODEL` | `Qwen/Qwen2-7B-Instruct` | 本地翻译模型 ID |
| `LOCAL_LOAD_IN_4BIT` | `true` | 启用 4-bit 量化 |
| `LOCAL_LOAD_IN_8BIT` | `false` | 启用 8-bit 量化 |
| `DOWNLOAD_SOURCE` | `huggingface` | 模型下载源: `huggingface` 或 `modelscope` |
| `MODELSCOPE_CACHE_DIR` | (默认) | ModelScope 缓存目录 |
| `EMBEDDING_PROVIDER` | `openai` | 嵌入提供者: `openai` 或 `bge` |
| `BGE_MODEL_ID` | `BAAI/bge-base-zh-v1.5` | BGE 模型 ID |
| `OPENAI_API_KEY` | (空) | OpenAI API 密钥 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI API 地址 |
| `OPENAI_MODEL` | `gpt-4-turbo-preview` | OpenAI 对话模型 |
| `HF_ENDPOINT` | (默认) | HuggingFace 镜像站 |

### 模型下载源

配置面板提供「模型下载源」选项，LLM 和 BGE 共用：
- **HuggingFace Hub**: 默认，可通过 `HF_ENDPOINT` 设置镜像
- **ModelScope 魔搭社区**: 国内加速，需 `pip install modelscope`

## 记忆库存储

JSON 文件持久化，特性：
- **原子写入**: 先写 `.tmp` → `fsync` → `os.replace`，防止写入中断损坏
- **自动备份**: 每次保存前复制旧文件为 `.bak`，损坏时自动恢复
- **数据校验**: 加载时递归检查结构完整性，缺失字段自动补全
- **过期清理**: 摘要 30 天 / 论点 90 天自动淘汰
- **兼容迁移**: 旧格式论点（纯字符串）自动升级为新格式 `{text, time, chunk}`

## 翻译优化

- **评论截断**: 17 条正则自动检测并删除 Qwen 模型产生的"这段文字讲述了..."式段落总结
- **术语后处理**: 51 条历史学术术语表自动替换
- **标点规范化**: 英文标点 → 中文标点转换
- **上下文截断**: TM/RAG 引用控制在 300-400 字内，总 Prompt ≤ 2500 字
- **输入缓存**: MD5 键值缓存，最大 500 条

## 注意事项

- 本地模型首次启动需下载 (Qwen ~4GB, BGE ~102MB)
- ModelScope 模式需 `pip install modelscope`
- PDF 文件处理需 `pip install PyMuPDF`
- 显存要求: 4-bit 量化约 4-5GB，建议至少 6GB 显存的 GPU
- ChromaDB 数据持久化在 `chroma_db/` 目录
- 记忆库 JSON 文件在 `memory/` 目录，`.bak` 为自动备份
- 翻译流水线每 10 段自动保存到 `partial_output.txt`
- 章节缝合输出到 `final_output.md`
