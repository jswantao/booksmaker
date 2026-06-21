# 智能翻译与EPUB工作台 (Smart Translation & EPUB Workbench)

本地历史学术翻译系统 —— 知识库 + 记忆库双轨设计，支持离线批量翻译和 EPUB 电子书生成。

## 快速启动

### 后端 API 服务
```bash
# 1. 安装 Python 依赖
pip install -r backend/requirements.txt

# 2. 启动后端 API (端口 8008)
python run.py
# 或: cd backend && python app.py
```

### 前端 (Next.js)
```bash
# 3. 安装前端依赖
cd frontend && npm install

# 4. 启动前端开发服务器 (端口 3000)
npm run dev
# 访问 http://localhost:3000
```

启动后，在配置面板选择「本地模型 (Qwen2-7B-Instruct)」→「保存并测试」，首次会下载模型。

## 项目结构

```
├── run.py                           # 启动入口 (从根目录一键启动后端)
├── README.md
│
├── backend/                         # Python 后端 (FastAPI)
│   ├── app.py                       # FastAPI 应用工厂 + 入口
│   ├── config.py                    # 全局配置与环境变量
│   ├── agents.py                    # Agent 定义 (4 个 Agent)
│   ├── model_providers.py           # LLM 抽象层
│   ├── embedding_providers.py       # 嵌入抽象层
│   ├── requirements.txt             # Python 依赖
│   ├── api/                         # API 路由 (8 模块)
│   ├── core/                        # 核心基础设施 (3 模块)
│   ├── models/                      # Pydantic 数据模型
│   ├── services/                    # 业务服务 (10 模块)
│   └── utils/                       # 工具
│
├── frontend/                        # Next.js 前端 (独立项目)
│   ├── src/app/                     # 入口 + 布局
│   ├── src/components/              # React 组件 (35+)
│   ├── src/hooks/                   # TanStack Query hooks
│   ├── src/lib/                     # API 客户端
│   ├── src/stores/                  # Zustand 状态
│   └── src/types/                   # TS 类型定义
│
├── data/                            # 持久化数据库
├── chroma_db/                       # ChromaDB 向量库
├── uploads/                         # 文件上传
└── memory_banks/                    # 记忆库 JSON
```

## 技术栈

| 组件     | 技术                                       | 用途                          |
| -------- | ------------------------------------------ | ----------------------------- |
| Web 框架 | FastAPI + Uvicorn                          | API 服务和静态文件            |
| LLM      | Qwen2-7B-Instruct (bitsandbytes 4-bit NF4) | 本地翻译推理 (~4-5GB 显存)    |
| 嵌入     | BAAI/bge-base-zh-v1.5 (CPU)                | 本地语义向量                  |
| 向量库   | ChromaDB                                   | RAG 知识库 + 翻译记忆向量检索 |
| 记忆库   | JSON (原子写入 + 自动备份)                 | 术语公约 + 进度持久化         |
| 翻译记忆 | SQLite + ChromaDB 双存                     | 精确匹配 + 向量相似度         |
| 量化     | bitsandbytes 4-bit NF4                     | 降低显存占用                  |
| 下载     | HuggingFace / ModelScope 魔搭社区          | 模型下载（国内加速）          |
| EPUB     | ebooklib                                   |                               |
| 前端     | 原生 HTML/CSS/JS (ES Module)               | SPA 三标签页                  |

## 架构总览

```


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

| 轨道                      | 存储            | 内容                                  | 用途                            |
| ------------------------- | --------------- | ------------------------------------- | ------------------------------- |
| **知识库 (KB)**     | ChromaDB 向量库 | 历史专著按章切分片段                  | 翻译时检索 Top-2 最相关上下文   |
| **记忆库 (Memory)** | JSON 文件       | 术语公约 + 段落摘要 + 核心论点 + 进度 | 跨片段保持术语一致性 + 断点续译 |

### 模型选型

| 模型                  | 格式                   | 显存        | 用途     |
| --------------------- | ---------------------- | ----------- | -------- |
| Qwen2-7B-Instruct     | bitsandbytes 4-bit NF4 | ~4-5GB      | 翻译推理 |
| BAAI/bge-base-zh-v1.5 | FP32 (CPU)             | ~400MB 内存 | 语义嵌入 |

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
- Agent-KB 分配（为不同 Agent 绑定默认知识库：ParagraphTranslator / EpubReplacer / KBBuilder / LongTextTranslator）
- 文档上传（TXT/PDF）
- KB 选择器（翻译/EPUB 面板各自选择）

### 3. 翻译流水线 📋

## API 端点

### 配置

| 方法     | 路径                             | 说明               |
| -------- | -------------------------------- | ------------------ |
| GET/POST | `/api/config`                  | 获取/保存 API 配置 |
| GET      | `/api/config/embedding/status` | BGE 加载状态       |
| GET      | `/api/config/llm/status`       | LLM 加载状态       |
| POST     | `/api/config/embedding`        | 切换嵌入提供者     |

### 翻译

| 方法 | 路径                  | 说明                          |
| ---- | --------------------- | ----------------------------- |
| POST | `/api/translate`    | 单句翻译（TM + RAG + 后处理） |
|      |                       |                               |
| POST | `/api/replace_epub` | 替换 EPUB 内容                |
|      |                       |                               |

### 翻译记忆库 (TM)

| 方法   | 路径                | 说明           |
| ------ | ------------------- | -------------- |
| GET    | `/api/tm`         | 获取记忆列表   |
| POST   | `/api/tm/search`  | 搜索记忆       |
| POST   | `/api/tm`         | 手动添加翻译对 |
| DELETE | `/api/tm/{id}`    | 删除单条       |
| DELETE | `/api/tm/clear`   | 清空记忆库     |
| POST   | `/api/tm/reindex` | 重建向量索引   |

### 知识库 (KB)

| 方法       | 路径                      | 说明             |
| ---------- | ------------------------- | ---------------- |
| GET/POST   | `/api/kb`               | 获取/创建知识库  |
| PUT/DELETE | `/api/kb/{id}`          | 更新/删除知识库  |
| POST       | `/api/kb/{id}/upload`   | 上传文档到知识库 |
| GET/POST   | `/api/kb/groups`        | 获取/创建分组    |
| PUT/DELETE | `/api/kb/groups/{id}`   | 更新/删除分组    |
| POST       | `/api/knowledge/upload` | 上传知识文档     |
| GET        | `/api/knowledge`        | 知识库状态摘要   |

### 翻译流水线 (Pipeline)

| 方法 | 路径                               | 说明           |
| ---- | ---------------------------------- | -------------- |
|      |                                    |                |
|      |                                    |                |
| POST | `/api/pipeline/run`              | 启动翻译流水线 |
| POST | `/api/pipeline/pause/{kb_name}`  | 暂停流水线     |
| POST | `/api/pipeline/resume/{kb_name}` | 恢复流水线     |
| GET  | `/api/pipeline/status/{kb_name}` | 查询进度       |
| GET  | `/api/pipeline/result/{kb_name}` | 获取翻译结果   |
| POST | `/api/pipeline/stitch`           | 章节缝合       |
| GET  | `/api/pipeline/kbs`              | 列出可用知识库 |
| POST | `/api/pipeline/memory/init`      | 初始化记忆库   |
| GET  | `/api/pipeline/memory/{path}`    | 查询记忆库状态 |

## 配置

### 环境变量

| 变量                      | 默认值                        | 说明                                         |
| ------------------------- | ----------------------------- | -------------------------------------------- |
| `LLM_PROVIDER`          | `openai`                    | LLM 提供者:`openai` 或 `local`           |
| `LOCAL_TRANSLATE_MODEL` | `Qwen/Qwen2-7B-Instruct`    | 本地翻译模型 ID                              |
| `LOCAL_LOAD_IN_4BIT`    | `true`                      | 启用 4-bit 量化                              |
| `LOCAL_LOAD_IN_8BIT`    | `false`                     | 启用 8-bit 量化                              |
| `DOWNLOAD_SOURCE`       | `huggingface`               | 模型下载源:`huggingface` 或 `modelscope` |
| `MODELSCOPE_CACHE_DIR`  | (默认)                        | ModelScope 缓存目录                          |
| `EMBEDDING_PROVIDER`    | `openai`                    | 嵌入提供者:`openai` 或 `bge`             |
| `BGE_MODEL_ID`          | `BAAI/bge-base-zh-v1.5`     | BGE 模型 ID                                  |
| `OPENAI_API_KEY`        | (空)                          | OpenAI API 密钥                              |
| `OPENAI_BASE_URL`       | `https://api.openai.com/v1` | OpenAI API 地址                              |
| `OPENAI_MODEL`          | `gpt-4-turbo-preview`       | OpenAI 对话模型                              |
| `HF_ENDPOINT`           | (默认)                        | HuggingFace 镜像站                           |

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

## 注意事项

- 本地模型首次启动需下载 (Qwen ~4GB, BGE ~102MB)
- ModelScope 模式需 `pip install modelscope`
- PDF 文件处理需 `pip install PyMuPDF`
- 显存要求: 4-bit 量化约 4-5GB，建议至少 6GB 显存的 GPU
- ChromaDB 数据持久化在 `chroma_db/` 目录
- 记忆库 JSON 文件在 `memory/` 目录，`.bak` 为自动备份
- 翻译流水线每 10 段自动保存到 `partial_output.txt`
- 章节缝合输出到 `final_output.md`
