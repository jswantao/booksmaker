// app.js — 智能翻译与EPUB工作台 入口模块
// ES Module: 导入所有业务模块，绑定事件，启动应用
import { Elements, cacheElements, initEvents } from './dom.js';
import { initTheme, toggleTheme } from './modules/theme.js';
import { loadConfig, saveConfig, clearConfig, onEmbeddingProviderChange, onLlmProviderChange } from './modules/config-panel.js';
import { submitTask } from './modules/translator.js';
import { getClickHandlers, getChangeHandlers, refreshKBManager, refreshKbSelectors } from './modules/kb-manager.js';
import { refreshTm, deleteTm, clearTm, searchTm, addTmPair, refreshKnowledge, scheduleTmPoll, scheduleKbPoll } from './modules/tm-manager.js';
import { switchTab, switchMainTab, clearOutput, copyOutput } from './ui.js';
import { AppState } from './state.js';

// ---- 组装事件处理器 ----
function buildClickHandlers() {
    return Object.assign(
        {
            'toggle-theme':          () => toggleTheme(),
            'switch-main-tab':       (el) => switchMainTab(el.dataset.param),
            'switch-tab':            (el) => switchTab(el.dataset.param),
            'save-config':           () => saveConfig(),
            'clear-config':          () => clearConfig(),
            'translate':             (el) => submitTask('translate', el),
            'generate-epub':         (el) => submitTask('generate-epub', el),
            'replace-epub':          (el) => submitTask('replace-epub', el),
            'clear-output':          (el) => clearOutput(el.dataset.param),
            'copy-output':           (el) => copyOutput(el.dataset.param),
            'search-tm':             () => searchTm(),
            'clear-tm':              () => clearTm(),
            'refresh-tm':            () => refreshTm(),
            'add-tm-pair':           () => addTmPair(),
            'refresh-knowledge':     () => refreshKnowledge(),
            'delete-tm':             (el) => deleteTm(el.dataset.param),
            'load-example-translation': () => {
                const ta = document.getElementById('replaceTranslation');
                if (ta) ta.value = ta.placeholder || '示例文本加载失败';
            },
            'load-example-epub': () => {
                const ta = document.getElementById('replaceEpubCode');
                if (ta) ta.value = ta.placeholder || '示例EPUB代码加载失败';
            },
        },
        getClickHandlers()
    );
}

function buildChangeHandlers() {
    return Object.assign(
        {
            'embedding-provider': () => onEmbeddingProviderChange(),
            'llm-provider':        () => onLlmProviderChange(),
        },
        getChangeHandlers()
    );
}

// ---- 可见性处理 ----
function onVisibilityChange(hidden) {
    if (hidden) {
        clearTimeout(AppState.tmPollTimer);
        clearTimeout(AppState.kbPollTimer);
    } else {
        refreshTm();
        refreshKnowledge();
        scheduleTmPoll();
        scheduleKbPoll();
        // 重新可见时检查 BGE 状态
        const providerSelect = document.getElementById('embeddingProvider');
        if (providerSelect && providerSelect.value === 'bge') {
            onEmbeddingProviderChange();
        }
    }
}

// ---- 键盘特殊处理 ----
function onKeyDown(e) {
    if (e.key === 'Enter') {
        const target = e.target;
        if (target.id === 'tmSearchInput') { e.preventDefault(); searchTm(); }
        else if (target.id === 'tmAddSource' || target.id === 'tmAddTarget') { e.preventDefault(); addTmPair(); }
    }
}

// ---- 初始化 ----
function init() {
    cacheElements();
    initTheme();
    loadConfig();
    refreshKnowledge();
    refreshTm();
    refreshKBManager();
    refreshKbSelectors();

    // 注册事件
    initEvents({
        click: buildClickHandlers(),
        change: buildChangeHandlers(),
        visibilityChange: onVisibilityChange,
    });

    // 额外键盘事件
    document.addEventListener('keydown', onKeyDown);

    // 智能轮询
    scheduleTmPoll();
    scheduleKbPoll();
}

document.addEventListener('DOMContentLoaded', init);
