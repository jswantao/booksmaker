// utils.js — 纯工具函数（无副作用，不依赖 DOM）
// 模块职责：字符串处理、哈希计算、通用辅助

/**
 * HTML 转义，防止 XSS
 */
export function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/`/g, '&#96;');
}

/**
 * 简单字符串哈希（用于轮询变更检测）
 */
export function computeHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash |= 0;
    }
    return String(hash);
}

/**
 * 自适应轮询间隔（无变化时指数退避）
 */
export function adjustInterval(current, hash, lastHash, min, max) {
    if (hash === lastHash) return Math.min(current + 5000, max);
    return min;
}

/**
 * 防抖
 */
export function debounce(fn, ms = 300) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}
