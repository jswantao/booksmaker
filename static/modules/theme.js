// modules/theme.js — 暗色/亮色模式
import { Elements } from '../dom.js';
import { LS_KEY, CSS_CLASS } from '../config.js';

export function initTheme() {
    if (localStorage.getItem(LS_KEY.darkMode) === 'true') {
        document.body.classList.add(CSS_CLASS.dark);
        if (Elements.themeToggle) Elements.themeToggle.textContent = '☀️ 亮色模式';
    }
}

export function toggleTheme() {
    const isDark = document.body.classList.toggle(CSS_CLASS.dark);
    if (Elements.themeToggle) {
        Elements.themeToggle.textContent = isDark ? '☀️ 亮色模式' : '🌙 暗色模式';
    }
    localStorage.setItem(LS_KEY.darkMode, isDark);
}
