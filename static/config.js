// config.js — 集中常量定义
// 模块职责：所有魔法字符串统一管理，其他模块从此导入

// ---- API 路径 ----
export const API_PATH = {
    config:       '/api/config',
    translate:    '/api/translate',
    generateEpub: '/api/generate_epub',
    replaceEpub:  '/api/replace_epub',
    tmList:       '/api/tm',
    tmSearch:     '/api/tm/search',
    tmClear:      '/api/tm/clear',
    tmAdd:        '/api/tm',
    kb:           '/api/kb',
    kbGroups:     '/api/kb/groups',
    knowledge:    '/api/knowledge',
    knowledgeUpload: '/api/knowledge/upload',
    embeddingStatus: '/api/config/embedding/status',
    llmStatus: '/api/config/llm/status',
    epubDownload: '/api/download/epub',
};

// ---- 默认值 ----
export const DEFAULTS = {
    baseUrl:   'https://api.openai.com/v1',
    model:     'gpt-4-turbo-preview',
    embedding: 'text-embedding-ada-002',
    bgeModel:  'BAAI/bge-base-zh-v1.5',
};

// ---- localStorage key ----
export const LS_KEY = {
    baseUrl:    'api_base_url',
    model:      'api_model',
    embedding:  'api_embedding',
    provider:   'embedding_provider',
    llmProvider:'llm_provider',
    localTranslate: 'local_translate_model',
    localEpub:  'local_epub_model',
    darkMode:   'darkMode',
};

// ---- CSS 类名 ----
export const CSS_CLASS = {
    active:   'active',
    hidden:   'hidden',
    dark:     'dark',
    copied:   'copied',
    collapsed:'collapsed',
    status:   'status',
    emptyState:   'empty-state',
    emptyStateSm: 'empty-state-sm',
};

// ---- 示例文本 ----
export const EXAMPLE_TRANSLATION = '';  // 占位，由 HTML 预填充
export const EXAMPLE_EPUB = '';         // 占位，由 HTML 预填充
export const POLL_CONFIG = {
    MIN_INTERVAL: 10000,
    MAX_INTERVAL: 30000,
};

// ---- HTML 片段 ----
export const HTML = {
    loading: '<span class="loader"></span>',
    emptyTm: '<div class="empty-state">暂无翻译记忆，开始翻译后会自动积累</div>',
    emptyKb: '<div class="empty-state">暂无知识库，点击上方按钮创建</div>',
    emptyKbGroup: '<div class="empty-state-sm">此分组暂无知识库</div>',
    emptyDocs: '<div class="empty-state-sm">暂无知识文档</div>',
    defaultKbHint: '<span class="kb-default-hint">使用智能体默认知识库</span>',
};
