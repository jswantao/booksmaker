// modules/config-panel.js — API 配置面板
import { Elements, $ } from '../dom.js';
import { API_PATH, DEFAULTS, LS_KEY } from '../config.js';
import { loadConfig as apiLoadConfig, saveConfig as apiSaveConfig, clearConfig as apiClearConfig, fetchEmbeddingStatus, fetchLlmStatus } from '../api.js';

// 仅此模块需要的元素引用
function getInputs() {
    return {
        apiKey:           $('apiKey'),
        apiBaseUrl:       $('apiBaseUrl'),
        apiModel:         $('apiModel'),
        apiEmbedding:     $('apiEmbedding'),
        embedProvider:    $('embeddingProvider'),
        llmProvider:      $('llmProvider'),
        localTranslate:   $('localTranslateModel'),
        localEpub:        $('localEpubModel'),
    };
}

function setConfigStatus(msg, className) {
    const el = Elements.configStatus;
    if (!el) return;
    el.textContent = msg;
    el.className = 'config-status-msg ' + (className || 'muted');
}

function setBadge(status, text) {
    const el = Elements.apiStatusBadge;
    if (!el) return;
    el.className = 'api-status ' + status;
    el.textContent = text;
}

export function toggleApiConfig() {
    const grid = $('apiConfigGrid');
    const btn = $('apiConfigToggleBtn');
    if (!grid || !btn) return;

    if (grid.style.display === 'none') {
        grid.style.display = 'grid';
        btn.textContent = '收起面板 ⬆️';
    } else {
        grid.style.display = 'none';
        btn.textContent = '⚙️ 修改配置 (已折叠)';
    }
}

export function updateConfigSummary() {
    const summary = $('configSummaryText');
    if (!summary) return;
    const inputs = getInputs();
    const llmProv = inputs.llmProvider.value;
    const embedProv = inputs.embedProvider.value;

    let llmStr = llmProv === 'local' ? `本地 (${inputs.localTranslate.value})` : `OpenAI (${inputs.apiModel.value})`;
    let embedStr = embedProv === 'bge' ? '本地 BGE 向量' : 'OpenAI 向量';

    summary.textContent = `⚡ 当前驱动：${llmStr} | ${embedStr}`;
}

// ---- 保存 ----
export async function saveConfig() {
    const inputs = getInputs();
    const llmProvider = inputs.llmProvider.value;
    const apiKey = inputs.apiKey.value.trim();

    // 本地模式不需要 API key
    if (llmProvider !== 'local' && !apiKey) {
        setConfigStatus('⚠️ 请填写API Key', 'error');
        return;
    }

    setConfigStatus('⏳ 测试连接中...', 'pending');

    try {
        const result = await apiSaveConfig({
            api_key: apiKey,
            base_url: inputs.apiBaseUrl.value.trim() || DEFAULTS.baseUrl,
            model_name: inputs.apiModel.value.trim() || DEFAULTS.model,
            embedding_model: inputs.apiEmbedding.value.trim() || DEFAULTS.embedding,
            embedding_provider: inputs.embedProvider.value,
            bge_model_id: DEFAULTS.bgeModel,
            llm_provider: llmProvider,
            local_translate_model: inputs.localTranslate.value.trim() || 'Qwen/Qwen2.5-1.5B-Instruct',
            local_epub_model: inputs.localEpub.value.trim(),
        });
        if (result.success) {
            setConfigStatus('✅ ' + result.message, 'success');
            setBadge('ready', '✅ 已配置');
            updateConfigSummary();
            setTimeout(() => {
                const grid = $('apiConfigGrid');
                const btn = $('apiConfigToggleBtn');
                if (grid && btn) {
                    grid.style.display = 'none';
                    btn.textContent = '⚙️ 修改配置 (已折叠)';
                }
            }, 1000);
            localStorage.setItem(LS_KEY.baseUrl, inputs.apiBaseUrl.value.trim());
            localStorage.setItem(LS_KEY.model, inputs.apiModel.value.trim());
            localStorage.setItem(LS_KEY.embedding, inputs.apiEmbedding.value.trim());
            localStorage.setItem(LS_KEY.provider, inputs.embedProvider.value);
            localStorage.setItem(LS_KEY.llmProvider, llmProvider);
            localStorage.setItem(LS_KEY.localTranslate, inputs.localTranslate.value.trim());
            localStorage.setItem(LS_KEY.localEpub, inputs.localEpub.value.trim());
            if (llmProvider === 'local') {
                checkLlmStatus();
            }
        } else {
            setConfigStatus('❌ ' + result.error, 'error');
            setBadge('error', '❌ 连接失败');
        }
    } catch (e) {
        setConfigStatus('❌ 网络错误：' + e.message, 'error');
    }
}

// ---- 清除 ----
export function clearConfig() {
    const inputs = getInputs();
    inputs.apiKey.value = '';
    inputs.apiBaseUrl.value = DEFAULTS.baseUrl;
    inputs.apiModel.value = DEFAULTS.model;
    inputs.apiEmbedding.value = DEFAULTS.embedding;
    inputs.embedProvider.value = 'openai';
    inputs.llmProvider.value = 'openai';
    setConfigStatus('已清除', 'muted');
    setBadge('pending', '⏳ 未配置');
    [LS_KEY.baseUrl, LS_KEY.model, LS_KEY.embedding, LS_KEY.provider, LS_KEY.llmProvider].forEach(k => localStorage.removeItem(k));
    // 重置本地模型字段
    inputs.localTranslate.value = 'Qwen/Qwen2.5-1.5B-Instruct';
    inputs.localEpub.value = '';
    onEmbeddingProviderChange();
    onLlmProviderChange();
    apiClearConfig({
        api_key: '', base_url: DEFAULTS.baseUrl, model_name: DEFAULTS.model,
        embedding_model: DEFAULTS.embedding, embedding_provider: 'openai', bge_model_id: DEFAULTS.bgeModel,
        llm_provider: 'openai', local_translate_model: '', local_epub_model: ''
    });
}

// ---- 加载 ----
export async function loadConfig() {
    try {
        const data = await apiLoadConfig();
        if (data.is_configured) {
            setBadge('ready', '✅ 已配置');
            setTimeout(() => {
                updateConfigSummary();
                const grid = $('apiConfigGrid');
                const btn = $('apiConfigToggleBtn');
                if (grid && btn) {
                    grid.style.display = 'none';
                    btn.textContent = '⚙️ 修改配置 (已折叠)';
                }
            }, 100);
        } else {
            const grid = $('apiConfigGrid');
            const btn = $('apiConfigToggleBtn');
            if (grid && btn) {
                grid.style.display = 'grid';
                btn.textContent = '收起面板 ⬆️';
            }
        }

        const inputs = getInputs();
        const baseUrl = localStorage.getItem(LS_KEY.baseUrl);
        const model = localStorage.getItem(LS_KEY.model);
        const embedding = localStorage.getItem(LS_KEY.embedding);
        const provider = localStorage.getItem(LS_KEY.provider) || 'openai';
        const llmProv = localStorage.getItem(LS_KEY.llmProvider) || 'openai';
        const localTrans = localStorage.getItem(LS_KEY.localTranslate) || data.local_translate_model;
        const localEpub = localStorage.getItem(LS_KEY.localEpub) || data.local_epub_model;

        if (baseUrl) inputs.apiBaseUrl.value = baseUrl;
        if (model) inputs.apiModel.value = model;
        if (embedding) inputs.apiEmbedding.value = embedding;
        inputs.embedProvider.value = provider;
        inputs.llmProvider.value = llmProv;
        if (localTrans) inputs.localTranslate.value = localTrans;
        if (localEpub !== undefined && localEpub !== null) inputs.localEpub.value = localEpub;

        onEmbeddingProviderChange();
        onLlmProviderChange();
    } catch (e) { console.error('加载配置失败', e); }
}

// ---- Embedding 提供者切换 ----
export function onLlmProviderChange() {
    const provider = (getInputs().llmProvider || {}).value || 'openai';
    const isLocal = provider === 'local';
    const openaiGroup = $('openaiModelGroup');
    const localGroup = $('localModelConfig');
    const apiKeyInput = $('apiKey');
    const apiBaseUrl = $('apiBaseUrl');
    const llmStatusDiv = $('llmStatus');

    // 隐藏/显示 OpenAI 专属字段
    if (openaiGroup) openaiGroup.style.display = isLocal ? 'none' : 'block';
    // 隐藏/显示 API Base URL
    if (apiBaseUrl) {
        const wrapper = apiBaseUrl.parentElement;
        if (wrapper) wrapper.style.display = isLocal ? 'none' : 'block';
    }
    // 本地模型配置
    if (localGroup) localGroup.style.display = isLocal ? 'block' : 'none';
    // 状态
    if (llmStatusDiv) llmStatusDiv.style.display = isLocal ? 'block' : 'none';

    // 本地模式 API key 非必填，OpenAI 模式必填
    if (apiKeyInput) {
        apiKeyInput.required = !isLocal;
        if (isLocal && !apiKeyInput.value.trim()) {
            apiKeyInput.placeholder = '本地模式无需 API Key';
        } else {
            apiKeyInput.placeholder = 'sk-... 输入您的API密钥';
        }
    }

    if (isLocal) {
        checkLlmStatus();
    }
}

async function checkLlmStatus() {
    try {
        const provider = (getInputs().llmProvider || {}).value || 'openai';
        if (provider !== 'local') return;

        const data = await fetchLlmStatus();
        const llmStatusText = $('llmStatusText');
        if (!llmStatusText) return;

        if (data.success && data.status) {
            const transStatus = (data.status.translate || {}).status || 'idle';
            const transError = (data.status.translate || {}).error;

            if (transStatus === 'idle') {
                llmStatusText.textContent = '📦 本地 LLM 尚未加载，点击上方「保存并测试」即可在后台异步加载';
            } else if (transStatus === 'downloading' || transStatus === 'loading') {
                llmStatusText.textContent = '⏳ 正在后台异步加载本地 LLM 模型 (可能需要数分钟)...';
                setTimeout(checkLlmStatus, 2000);
            } else if (transStatus === 'ready') {
                llmStatusText.textContent = '✅ 本地 LLM 模型已就绪 (以原生 FP16 加载)';
            } else if (transStatus === 'error') {
                llmStatusText.textContent = '❌ 本地 LLM 加载失败: ' + (transError || '未知错误');
            }
        }
    } catch (e) { console.error('检查LLM状态失败', e); }
}

export function onEmbeddingProviderChange() {
    const provider = (getInputs().embedProvider || {}).value || 'openai';
    const openaiGroup = $('openaiEmbeddingGroup');
    if (openaiGroup) openaiGroup.style.display = provider === 'openai' ? 'block' : 'none';

    if (provider === 'bge') {
        if (Elements.bgeStatus) Elements.bgeStatus.style.display = 'block';
        checkBgeStatus();
    } else {
        if (Elements.bgeStatus) Elements.bgeStatus.style.display = 'none';
    }
}

async function checkBgeStatus() {
    try {
        const data = await fetchEmbeddingStatus();
        if (!Elements.bgeStatusText) return;
        if (data.status === 'idle') {
            Elements.bgeStatusText.textContent = '📦 BGE 模型尚未加载，将在首次使用时自动下载 (~102MB)';
            Elements.bgeStatusSpinner.style.display = 'none';
        } else if (data.status === 'downloading' || data.status === 'loading') {
            Elements.bgeStatusText.textContent = '⏳ 正在加载 BGE 模型...';
            Elements.bgeStatusSpinner.style.display = 'inline';
            setTimeout(checkBgeStatus, 2000);
        } else if (data.status === 'ready') {
            Elements.bgeStatusText.textContent = '✅ BGE 模型已就绪';
            Elements.bgeStatusSpinner.style.display = 'none';
        } else if (data.status === 'error') {
            Elements.bgeStatusText.textContent = '❌ 加载失败: ' + (data.error || '未知错误');
            Elements.bgeStatusSpinner.style.display = 'none';
        }
    } catch (e) { console.error('检查BGE状态失败', e); }
}
