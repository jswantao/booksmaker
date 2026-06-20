# 智能翻译与EPUB工作台 (Smart Translation & EPUB Workbench)

基于 FastAPI + ChromaDB + OpenAI API + BGE 本地嵌入 的 Web 应用，用于英文历史书籍的智能中译和 EPUB 电子书生成。

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python app.py
# 访问 http://localhost:8000
```

## 项目结构

```
├── app.py                  # 主后端 (FastAPI, 端口 8000)
├── agents.py               # 智能体定义 (Agent dataclass + 系统提示词 + 工具策略)
├── embedding_providers.py  # 嵌入提供者抽象层 (OpenAI + BGE)
├── templates/
│   └── index.html          # 前端单页面 UI
├── static/
│   └── app.js              # 前端 JS (IIFE + 事件委托)
├── requirements.txt        # Python 依赖
├── chroma_db/              # ChromaDB 向量数据库 (自动创建)
├── uploads/                # 文件上传目录
└── translation_memory.db   # SQLite 翻译记忆库 (自动创建)
```

## 技术栈

- **后端**: Python FastAPI + Uvicorn
- **AI**: OpenAI API (可配置 base_url，兼容多种模型)
- **本地嵌入**: BAAI BGE 模型 (sentence-transformers 本地加载，默认 `bge-base-zh-v1.5`)
- **向量库**: ChromaDB (持久化，RAG 知识库 + 翻译记忆向量检索)
- **翻译记忆**: SQLite (结构化元数据) + ChromaDB (向量相似度)
- **前端**: 纯 HTML/CSS/JS (Jinja2 模板)，支持暗色模式
- **EPUB**: ebooklib 生成标准 .epub 文件

## 架构

### 两个 AI 智能体

1. **世界史专家** — 英文历史文献 → 中文翻译
   - 系统提示词: 学术风格、专有名词公认译名、忠实原文
   - RAG 知识库: `history_knowledge` 集合
   - TM 增强: 翻译记忆库保持一致性

2. **EPUB编辑** — 生成 EPUB 代码 / 替换 EPUB 内容
   - 系统提示词: EPUB 标准规范、保持原有结构
   - RAG 知识库: `epub_knowledge` 集合

### 翻译流程

```
用户输入 → 精确TM匹配 → 模糊TM匹配(向量) → RAG检索 → LLM翻译 → 存入TM
```

### 嵌入提供者架构

```
EmbeddingManager (单例，线程安全切换)
├── OpenAIEmbeddingProvider     # 远程 API: text-embedding-ada-002 等
└── BGEEmbeddingProvider        # 本地模型: BAAI/bge-base-zh-v1.5
        └── 惰性加载，首次调用 embed() 时下载模型
        └── 查询自动添加 BGE 指令前缀
        └── 输出 L2 归一化向量
```

配置方式：
- 环境变量: `EMBEDDING_PROVIDER=bge`, `BGE_MODEL_ID=BAAI/bge-base-zh-v1.5`
- Web UI: API 配置面板下拉选择器

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 首页 |
| POST | `/api/config` | 配置 API 密钥和模型 |
| GET | `/api/config` | 获取当前配置状态 |
| POST | `/api/translate` | 翻译文本 |
| POST | `/api/generate_epub` | 生成 EPUB 代码 + 文件 |
| POST | `/api/replace_epub` | 替换 EPUB 内容 + 文件 |
| GET | `/api/download/epub/{filename}` | 下载 EPUB 文件 |
| POST | `/api/tm/search` | 搜索翻译记忆 |
| GET | `/api/tm` | 获取翻译记忆列表 |
| POST | `/api/tm/add` | 手动添加翻译对 |
| DELETE | `/api/tm/{id}` | 删除单条记忆 |
| DELETE | `/api/tm/clear` | 清空记忆库 |
| POST | `/api/tm/reindex` | 重建向量索引 |
| POST | `/api/upload_knowledge` | 上传知识文档 |
| GET | `/api/knowledge/{agent_name}` | 获取知识库状态 |

## 配置

### API 配置
- 通过 Web UI 配置，或设置环境变量:
  - `OPENAI_API_KEY` — API 密钥
  - `OPENAI_BASE_URL` — API 基础 URL (默认 `https://api.openai.com/v1`)

### 默认模型
- 对话模型: `gpt-4-turbo-preview`
- Embedding 模型: `text-embedding-ada-002`

## 翻译记忆库 (TM)

- **SQLite**: 存储结构化数据 (创建时间、使用次数、语言对)
- **ChromaDB**: 存储向量嵌入，用于相似度检索
- **回退机制**: API key 未配置时使用 Jaccard 文本相似度
- `source_hash` (MD5) 桥接两套存储系统

## 注意事项

- API key 存储在服务端内存，重启后需重新配置（除非设置环境变量）
- ChromaDB 数据持久化在 `chroma_db/` 目录
- 上传的知识文档按段落（`\n\n`）分块存储
- 支持 Ctrl+Enter 快捷键提交翻译/EPUB
