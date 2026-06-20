// modules/tm-manager.js — 翻译记忆库管理
import { Elements, $ } from '../dom.js';
import { POLL_CONFIG } from '../config.js';
import { fetchTmList, deleteTmEntry, clearTmAll, addTmPair as apiAddTmPair, fetchKnowledge } from '../api.js';
import { renderTmList } from '../ui.js';
import { escapeHtml, computeHash, adjustInterval } from '../utils.js';
import { AppState } from '../state.js';

// ---- TM 刷新 ----
export async function refreshTm() {
    try {
        const data = await fetchTmList();
        if (data.success) {
            Elements.tmCount.textContent = (data.total || 0) + ' 条';
            renderTmList(data.results || []);
        }
    } catch (e) {
        console.error('刷新翻译记忆库失败', e);
    }
}

// ---- TM CRUD ----
export async function deleteTm(id) {
    if (!confirm('确定要删除这条翻译记忆吗？')) return;
    try {
        const data = await deleteTmEntry(id);
        if (data.success) refreshTm();
        else alert('删除失败：' + data.error);
    } catch (e) { alert('网络错误：' + e.message); }
}

export async function clearTm() {
    if (!confirm('确定要清空所有翻译记忆吗？此操作不可撤销！')) return;
    try {
        const data = await clearTmAll();
        if (data.success) { refreshTm(); alert('已清空翻译记忆库'); }
        else alert('清空失败：' + data.error);
    } catch (e) { alert('网络错误：' + e.message); }
}

export async function searchTm() {
    const inputEl = $('tmSearchInput');
    const query = inputEl.value.trim();
    if (!query) { refreshTm(); return; }
    try {
        const resp = await fetch(`/api/tm/search?q=${encodeURIComponent(query)}`);
        const data = await resp.json();
        if (data.success) {
            renderTmList(data.results || []);
            Elements.tmCount.textContent = '搜索结果: ' + (data.results || []).length + ' 条';
        }
    } catch (e) { alert('搜索失败：' + e.message); }
}

export async function addTmPair() {
    const sourceInput = $('tmAddSource');
    const targetInput = $('tmAddTarget');
    const source = sourceInput.value.trim();
    const target = targetInput.value.trim();
    if (!source || !target) { alert('请填写原文和译文'); return; }
    try {
        const result = await apiAddTmPair(source, target);
        if (result.success) {
            sourceInput.value = '';
            targetInput.value = '';
            refreshTm();
        } else { alert('添加失败：' + result.error); }
    } catch (e) { alert('网络错误：' + e.message); }
}

// ---- 知识库状态刷新 ----
export async function refreshKnowledge() {
    try {
        const data = await fetchKnowledge();
        Elements.kbHistCount.textContent = data.history_count || 0;
        Elements.kbEpubCount.textContent = data.epub_count || 0;
        // 使用 ui 模块渲染知识列表（避免循环依赖，在这里内联渲染即可）
        renderKnowledgeLists(data);
    } catch (e) { console.error('刷新知识库失败', e); }
}

function renderKnowledgeLists(data) {
    ['translateKnowledgeList', 'epubKnowledgeList'].forEach((listId, i) => {
        const container = document.getElementById(listId);
        if (!container) return;
        const items = i === 0 ? (data.history || []) : (data.epub || []);
        if (!items.length) {
            container.innerHTML = '<div class="empty-state-sm">暂无知识文档</div>';
        } else {
            container.innerHTML = '<ul>' + items.map(item => '<li>📄 ' + escapeHtml(item.name || item) + '</li>').join('') + '</ul>';
        }
    });
}

// ---- 智能轮询 ----
export function scheduleTmPoll() {
    AppState.tmPollTimer = setTimeout(async () => {
        try {
            const resp = await fetch('/api/tm?limit=100');
            const text = await resp.text();
            const hash = computeHash(text);
            AppState.tmPollIntervalMs = adjustInterval(
                AppState.tmPollIntervalMs, hash, AppState.tmLastHash,
                POLL_CONFIG.MIN_INTERVAL, POLL_CONFIG.MAX_INTERVAL
            );
            AppState.tmLastHash = hash;
            const data = JSON.parse(text);
            if (data.success) {
                Elements.tmCount.textContent = (data.total || 0) + ' 条';
                renderTmList(data.results || []);
            }
        } catch (e) { console.error('轮询翻译记忆库失败', e); }
        scheduleTmPoll();
    }, AppState.tmPollIntervalMs);
}

export function scheduleKbPoll() {
    AppState.kbPollTimer = setTimeout(async () => {
        try {
            const resp = await fetch('/api/knowledge');
            const text = await resp.text();
            const hash = computeHash(text);
            AppState.kbPollIntervalMs = adjustInterval(
                AppState.kbPollIntervalMs, hash, AppState.kbLastHash,
                POLL_CONFIG.MIN_INTERVAL, POLL_CONFIG.MAX_INTERVAL
            );
            AppState.kbLastHash = hash;
            const data = JSON.parse(text);
            Elements.kbHistCount.textContent = data.history_count || 0;
            Elements.kbEpubCount.textContent = data.epub_count || 0;
        } catch (e) { console.error('轮询知识库失败', e); }
        scheduleKbPoll();
    }, AppState.kbPollIntervalMs);
}
