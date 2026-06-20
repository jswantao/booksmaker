// ui.js — 渲染与视觉反馈
// 模块职责：所有 DOM 渲染函数，不含业务逻辑
import { Elements, $ } from './dom.js';
import { escapeHtml } from './utils.js';
import { CSS_CLASS, HTML } from './config.js';

// ---- 状态与输出 ----
export function showStatus(elementId, message, type) {
    const el = $(elementId);
    if (!el) return;
    el.textContent = message;
    el.className = CSS_CLASS.status + ' ' + (type || '');
}

export function clearOutput(id) {
    const el = $(id);
    if (el) el.innerHTML = '';
}

export async function copyOutput(outputId) {
    const outputEl = $(outputId);
    if (!outputEl) return;
    const pre = outputEl.querySelector('pre');
    const text = pre ? pre.textContent : outputEl.textContent;
    try {
        await navigator.clipboard.writeText(text);
        const btn = outputEl.querySelector('.copy-btn');
        if (btn) {
            btn.textContent = '✅ 已复制!';
            btn.classList.add(CSS_CLASS.copied);
            setTimeout(() => {
                btn.textContent = btn.dataset.originalText || '📋 复制';
                btn.classList.remove(CSS_CLASS.copied);
            }, 2000);
        }
    } catch (err) {
        alert('复制失败: ' + err.message);
    }
}

// ---- 按钮加载状态 ----
export function setBtnLoading(actionEl, loading) {
    if (!actionEl) return;
    actionEl.dataset.loading = loading ? 'true' : 'false';
    actionEl.disabled = loading;
}

export function isBtnLoading(actionEl) {
    return actionEl && actionEl.dataset.loading === 'true';
}

// ---- 标签切换 ----
export function switchTab(tab) {
    document.querySelectorAll('.tab-content').forEach(e => e.classList.remove(CSS_CLASS.active));
    document.querySelectorAll('.tab-group button').forEach(e => {
        e.classList.remove(CSS_CLASS.active);
        e.setAttribute('aria-selected', 'false');
    });
    const tabEl = document.getElementById('tab-' + tab);
    if (tabEl) tabEl.classList.add(CSS_CLASS.active);
    const btn = document.querySelector(`.tab-group button[data-tab="${tab}"]`);
    if (btn) { btn.classList.add(CSS_CLASS.active); btn.setAttribute('aria-selected', 'true'); }
}

export function switchMainTab(tab) {
    document.querySelectorAll('.maintab-content').forEach(e => e.classList.remove(CSS_CLASS.active));
    document.querySelectorAll('.main-tabs button').forEach(e => {
        e.classList.remove(CSS_CLASS.active);
        e.setAttribute('aria-selected', 'false');
    });
    const contentEl = document.getElementById('maintab-' + tab);
    if (contentEl) contentEl.classList.add(CSS_CLASS.active);
    const btn = document.querySelector(`.main-tabs button[data-maintab="${tab}"]`);
    if (btn) { btn.classList.add(CSS_CLASS.active); btn.setAttribute('aria-selected', 'true'); }
}

// ---- 模态框 ----
export function showModal(overlayId) {
    $(overlayId)?.classList.remove(CSS_CLASS.hidden);
}
export function hideModal(overlayId) {
    $(overlayId)?.classList.add(CSS_CLASS.hidden);
}

// ---- EPUB 输出渲染 ----
export function renderEpubOutput(result, outputElKey) {
    const el = Elements[outputElKey];
    if (!el) return;
    let html = '<pre>' + escapeHtml(result.epub_code) + '</pre>';
    if (result.download_url) {
        html += `<div class="mt-md">
            <a href="${escapeHtml(result.download_url)}" class="btn btn-success" download>📥 下载 EPUB 文件</a>
            <button class="btn btn-secondary copy-btn" data-action="copy-output" data-param="${outputElKey}">📋 复制代码</button>
        </div>`;
    }
    el.innerHTML = html;
}

// ---- 翻译记忆列表 ----
export function renderTmList(results) {
    const el = Elements.tmList;
    if (!el) return;
    if (!results || results.length === 0) {
        el.innerHTML = HTML.emptyTm;
        return;
    }
    el.innerHTML = results.map(item =>
        `<div class="tm-item">
            <span class="source">📝 ${escapeHtml(item.source)}</span><br>
            <span class="target">➜ ${escapeHtml(item.target)}</span>
            <span class="count"> | 使用 ${item.use_count} 次</span>
            <button class="delete-btn" data-action="delete-tm" data-param="${item.id}">✕</button>
        </div>`
    ).join('');
}

// ---- 知识库列表 ----
export function renderKnowledgeList(elementId, items) {
    const el = $(elementId);
    if (!el) return;
    if (!items || items.length === 0) {
        el.innerHTML = HTML.emptyDocs;
        return;
    }
    el.innerHTML = '<ul>' + items.map(item =>
        '<li>📄 ' + escapeHtml(item.name || item) + '</li>'
    ).join('') + '</ul>';
}

// ---- KB 管理面板渲染 ----
export function renderKBList(kbs, groups) {
    const el = Elements.kbManagerContent;
    if (!el) return;
    if (kbs.length === 0 && groups.length === 0) {
        el.innerHTML = HTML.emptyKb;
        return;
    }

    const kbByGroup = {};
    const ungrouped = [];
    kbs.forEach(kb => {
        if (kb.group_id) {
            if (!kbByGroup[kb.group_id]) kbByGroup[kb.group_id] = [];
            kbByGroup[kb.group_id].push(kb);
        } else {
            ungrouped.push(kb);
        }
    });

    let html = '';
    groups.forEach(g => {
        const groupKbs = kbByGroup[g.id] || [];
        const name = escapeHtml(g.name);
        html += `<div class="kb-group-header" data-action="toggle-kb-group">
            <span class="expand-icon">▼</span>
            <span>📁 ${name}</span>
            <span class="kb-count">(${groupKbs.length}个知识库)</span>
            <span style="flex:1;"></span>
            <span class="grp-actions" data-action="none">
                <button data-action="edit-group" data-param="${g.id}|${name}|${escapeHtml(g.description||'')}">✏️</button>
                <button class="btn-del" data-action="delete-group" data-param="${g.id}">🗑</button>
            </span></div>`;
        html += '<div class="kb-items">';
        if (groupKbs.length === 0) {
            html += HTML.emptyKbGroup;
        } else {
            groupKbs.forEach(kb => html += renderKBItem(kb));
        }
        html += '</div>';
    });

    if (ungrouped.length > 0) {
        html += `<div class="ungrouped-header">📂 未分组 (${ungrouped.length}个)</div>`;
        html += '<div class="kb-items">';
        ungrouped.forEach(kb => html += renderKBItem(kb));
        html += '</div>';
    }

    el.innerHTML = html;
}

export function renderKBItem(kb) {
    const embLabel = kb.embedding_model === 'bge' ? 'BGE本地' : kb.embedding_model === 'openai' ? 'OpenAI' : '默认';
    const name = escapeHtml(kb.name);
    const colName = escapeHtml(kb.collection_name);
    const desc = escapeHtml(kb.description || '');
    const gid = kb.group_id || '';
    const emb = kb.embedding_model || '';
    return `<div class="kb-item">
        <div class="kb-info">
            <div class="kb-name">📚 ${name}</div>
            <div class="kb-meta">${colName} · ${embLabel} · ${kb.document_count||0}条文档</div>
        </div>
        <div class="kb-actions">
            <button data-action="upload-kb" data-param="${kb.id}">📤 上传</button>
            <button data-action="edit-kb" data-param="${kb.id}|${name}|${desc}|${emb}|${gid}">✏️</button>
            <button class="btn-del" data-action="delete-kb" data-param="${kb.id}">🗑</button>
        </div></div>`;
}

// ---- KB 选择器渲染 ----
export function renderKbSelectorTags(panel, selected, kbs) {
    const tagsDiv = document.getElementById(panel + 'KbTags');
    if (!tagsDiv) return;
    if (selected.length === 0) {
        tagsDiv.innerHTML = HTML.defaultKbHint;
    } else {
        tagsDiv.innerHTML = selected.map(id => {
            const kb = kbs.find(k => k.id === id);
            return kb ? `<span class="kb-tag" data-action="remove-kb" data-panel="${panel}" data-kbid="${id}">📚 ${escapeHtml(kb.name)} ✕</span>` : '';
        }).join('');
    }
    tagsDiv.innerHTML += `<button class="btn btn-secondary kb-select-btn" data-action="show-kb-picker" data-param="${panel}">+ 选择</button>`;
}

export function populateGroupSelects(panel, groups) {
    const sel = document.getElementById(panel + 'GroupSelect');
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = '<option value="">按分组: 全部知识库</option>';
    groups.forEach(g => {
        sel.innerHTML += `<option value="${g.id}">📁 ${escapeHtml(g.name)}</option>`;
    });
    sel.value = currentVal;
}
