// dom.js — DOM 元素缓存 + 事件委托绑定
// 模块职责：集中管理 DOM 引用，注册 click/change/keydown 委托
import { CSS_CLASS } from './config.js';

// ---- 元素缓存 ----
export const Elements = {};

/**
 * 缓存跨函数高频引用的 DOM 元素
 */
export function cacheElements() {
    const ids = [
        'configStatus', 'apiStatusBadge',
        'translationOutput', 'epubOutput', 'replaceOutput',
        'tmCount', 'tmList', 'kbManagerContent',
        'kbHistCount', 'kbEpubCount',
        'bgeStatus', 'bgeStatusText', 'bgeStatusSpinner',
        'themeToggle',
    ];
    for (const id of ids) {
        Elements[id] = document.getElementById(id);
    }
}

// ---- 事件委托 ----
/** @type {Map<string, Function>} */
let _clickHandlers = null;
let _changeHandlers = null;

/**
 * 注册事件委托处理器
 */
export function initEvents(handlers) {
    _clickHandlers = handlers.click || {};
    _changeHandlers = handlers.change || {};

    // 点击委托
    document.addEventListener('click', (e) => {
        const actionEl = e.target.closest('[data-action]');
        if (!actionEl) return;
        const action = actionEl.dataset.action;
        const handler = _clickHandlers[action];
        if (handler) handler(actionEl);
    });

    // 变更委托
    document.addEventListener('change', (e) => {
        const changeAction = e.target.dataset.change;
        if (!changeAction) return;
        const handler = _changeHandlers[changeAction];
        if (handler) handler(e.target);
    });

    // 键盘委托
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            // 关闭所有模态框
            const overlays = document.querySelectorAll('.modal-overlay:not(.hidden)');
            if (overlays.length > 0) {
                overlays.forEach(ov => ov.classList.add(CSS_CLASS.hidden));
            }
        }
        // Enter 在特定输入框中触发操作
        if (e.key === 'Enter') {
            const target = e.target;
            if (target.tagName === 'INPUT' && target.type === 'text') {
                if (target.id === 'tmSearchInput' || target.id === 'tmAddSource' || target.id === 'tmAddTarget') {
                    e.preventDefault();
                }
            }
        }
    });

    // 页面可见性切换
    document.addEventListener('visibilitychange', () => {
        if (handlers.visibilityChange) handlers.visibilityChange(document.hidden);
    });
}

// ---- 辅助函数 ----
/**
 * 安全获取元素，带缓存
 */
export function $(id) {
    if (Elements[id]) return Elements[id];
    const el = document.getElementById(id);
    if (el) Elements[id] = el;
    return el;
}

/**
 * 设置元素文本和 CSS 类
 */
export function setStatus(elOrId, message, type) {
    const el = typeof elOrId === 'string' ? $(elOrId) : elOrId;
    if (!el) return;
    el.textContent = message;
    el.className = CSS_CLASS.status + ' ' + (type || '');
}
