// modules/memory-bank.js — 记忆库面板
// 模块职责：展示记忆库状态、术语表管理、搜索/筛选/导入/导出/初始化
import { $ } from '../dom.js';
import { escapeHtml, debounce } from '../utils.js';
import { pipelineGetMemory, pipelineInitMemory } from '../api.js';

// ---- 状态 ----
let _terms = [];          // 当前完整术语列表
let _filterMode = 'all';  // 'all' | 'seed' | 'auto'
let _memoryPath = '';     // 当前记忆库路径

// ---- 获取记忆库路径 ----
function getMemoryPath() {
    // 优先从流水线面板读取
    const pathInput = $('pipelineMemoryPath');
    if (pathInput && pathInput.value.trim()) return pathInput.value.trim();
    // 其次尝试著作名
    const bookName = $('translateBookName');
    if (bookName && bookName.value.trim()) {
        return 'memory/' + bookName.value.trim() + '_memory.json';
    }
    return _memoryPath;
}

// ---- 加载记忆库数据 ----
async function loadMemory() {
    const memPath = getMemoryPath();
    if (!memPath) {
        renderEmpty('请先在「翻译工作台」输入著作名，或在「流水线」中配置记忆库路径');
        return;
    }
    _memoryPath = memPath;

    // 更新路径显示
    const pathText = $('memoryPathText');
    if (pathText) pathText.textContent = memPath;

    try {
        const result = await pipelineGetMemory(memPath);
        if (!result.success && !result.terminology) {
            renderEmpty('记忆库尚未创建，请先运行翻译流水线或手动初始化');
            updateStats(null);
            return;
        }
        _terms = parseTerms(result);
        renderStats(result);
        renderTable();
    } catch (e) {
        renderEmpty('加载失败: ' + e.message);
    }
}

// ---- 解析术语数据 ----
function parseTerms(result) {
    const terms = [];
    const terminology = result.terminology || result.terms || {};
    if (Array.isArray(terminology)) {
        // 数组格式
        terminology.forEach(t => {
            terms.push({
                en: t.en || t.source || t.english || '',
                zh: t.zh || t.target || t.chinese || '',
                source: t.source_type || t.source_tag || 'auto',
            });
        });
    } else if (typeof terminology === 'object') {
        // 字典格式 { "english": "chinese" }
        for (const [en, zh] of Object.entries(terminology)) {
            terms.push({
                en,
                zh: typeof zh === 'string' ? zh : (zh?.translation || zh?.value || JSON.stringify(zh)),
                source: (typeof zh === 'object' && zh?.source_type) ? zh.source_type : 'auto',
            });
        }
    }
    return terms;
}

// ---- 渲染统计数据 ----
function renderStats(result) {
    const projectName = $('memoryProjectName');
    if (projectName) {
        const name = result.project_name || result.project || getMemoryPath()
            .replace(/^memory[\\/]/, '').replace(/_memory\.json$/, '');
        projectName.textContent = name || '--';
    }

    const totalEl = $('memoryTotalTerms');
    if (totalEl) totalEl.textContent = _terms.length;

    const seedHint = $('memorySeedHint');
    const seedCount = _terms.filter(t => t.source === 'seed').length;
    if (seedHint) seedHint.textContent = `含种子术语 ${seedCount} 条`;

    // 翻译进度
    const chaptersEl = $('memoryTranslatedChapters');
    const completed = result.completed_chapters || [];
    const totalChunks = (result.progress || {}).total_chunks || result.total_chunks || 0;
    const doneChunks = result.chunks_done || (result.progress || {}).chunks_done || 0;
    if (chaptersEl) chaptersEl.textContent = completed.length;

    const progressHint = $('memoryProgressHint');
    if (progressHint) {
        const pct = totalChunks > 0 ? Math.round(doneChunks / totalChunks * 100) : 0;
        progressHint.textContent = `进度 ${pct}% (${doneChunks}/${totalChunks} 段)`;
    }

    // 自动提取术语数
    const autoTermsEl = $('memoryAutoTerms');
    const autoCount = _terms.filter(t => t.source !== 'seed').length;
    if (autoTermsEl) autoTermsEl.textContent = autoCount;

    // 最近翻译信息
    const lastTranslateEl = $('memoryLastTranslate');
    const lastTimeEl = $('memoryLastTime');
    if (lastTranslateEl) {
        if (completed.length > 0) {
            const last = completed[completed.length - 1];
            lastTranslateEl.textContent = typeof last === 'string' ? last : (last.title || `第${last.chapter || last.index || '?'}章`);
        } else if (doneChunks > 0) {
            lastTranslateEl.textContent = `第 ${doneChunks} 段`;
        } else {
            lastTranslateEl.textContent = '--';
        }
    }
    if (lastTimeEl) {
        lastTimeEl.textContent = result.last_updated || result.updated_at || '';
    }
}

function updateStats(/* result */) {
    const totalEl = $('memoryTotalTerms');
    if (totalEl) totalEl.textContent = _terms.length;
}

// ---- 渲染术语表 ----
function renderTable() {
    const tbody = $('memoryTermTableBody');
    if (!tbody) return;

    let filtered = _terms;
    if (_filterMode === 'seed') {
        filtered = _terms.filter(t => t.source === 'seed');
    } else if (_filterMode === 'auto') {
        filtered = _terms.filter(t => t.source !== 'seed');
    }

    // 搜索过滤
    const searchInput = $('memorySearchInput');
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    if (query) {
        filtered = filtered.filter(t =>
            t.en.toLowerCase().includes(query) || t.zh.includes(query)
        );
    }

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state-sm">${
            _terms.length === 0
                ? '暂无术语数据，请先运行翻译或手动初始化记忆库'
                : '无匹配结果'
        }</td></tr>`;
        return;
    }

    tbody.innerHTML = filtered.map(t => {
        const sourceClass = t.source === 'seed' ? 'term-source-seed' : 'term-source-auto';
        const sourceLabel = t.source === 'seed' ? '种子' : '自动';
        return `<tr>
            <td class="term-en">${escapeHtml(t.en)}</td>
            <td class="term-zh">${escapeHtml(t.zh)}</td>
            <td><span class="term-source-badge ${sourceClass}">${sourceLabel}</span></td>
            <td><button class="btn btn-secondary btn-sm" data-action="memory-copy-term" data-param="${escapeHtml(t.en)}|${escapeHtml(t.zh)}" title="复制翻译对" style="font-size:0.75rem;padding:3px 8px;">复制</button></td>
        </tr>`;
    }).join('');
}

function renderEmpty(message) {
    const tbody = $('memoryTermTableBody');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state-sm">${escapeHtml(message)}</td></tr>`;
    }
    // 重置统计
    const ids = ['memoryTotalTerms', 'memoryAutoTerms'];
    ids.forEach(id => { const el = $(id); if (el) el.textContent = '0'; });
    const hintIds = ['memorySeedHint', 'memoryProgressHint', 'memoryLastTranslate', 'memoryLastTime'];
    hintIds.forEach(id => { const el = $(id); if (el) el.textContent = '--'; });
    const chaptersEl = $('memoryTranslatedChapters');
    if (chaptersEl) chaptersEl.textContent = '--';
}

// ---- 筛选 ----
function setFilter(mode) {
    _filterMode = mode;
    // 更新按钮视觉状态
    const buttons = document.querySelectorAll('[data-action="memory-filter"]');
    buttons.forEach(btn => {
        const isActive = btn.dataset.param === mode;
        if (isActive) {
            btn.style.background = 'color-mix(in srgb, var(--seed-primary) 8%, var(--card-bg) 92%)';
            btn.style.color = 'var(--seed-primary)';
            btn.style.borderColor = 'transparent';
        } else {
            btn.style.background = 'transparent';
            btn.style.color = 'var(--text-secondary)';
            btn.style.borderColor = 'var(--border)';
        }
    });
    renderTable();
}

// ---- 搜索 ----
function onSearch() {
    renderTable();
}

// ---- 导出术语 ----
function exportTerms() {
    if (_terms.length === 0) {
        alert('暂无术语数据可导出');
        return;
    }
    const data = {};
    _terms.forEach(t => { data[t.en] = t.zh; });
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const projectName = $('memoryProjectName')?.textContent || 'terminology';
    a.download = `${projectName}_terms.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// ---- 导入术语 ----
function importTerms() {
    const fileInput = $('memoryImportFile');
    if (!fileInput) return;
    fileInput.click();
}

async function handleImportFile(file) {
    if (!file) return;
    try {
        const text = await file.text();
        const data = JSON.parse(text);
        const imported = [];
        if (Array.isArray(data)) {
            data.forEach(item => {
                if (item.en && item.zh) imported.push(item);
                else if (item.source && item.target) {
                    imported.push({ en: item.source, zh: item.target, source: 'seed' });
                }
            });
        } else if (typeof data === 'object') {
            for (const [en, zh] of Object.entries(data)) {
                imported.push({ en, zh: typeof zh === 'string' ? zh : String(zh), source: 'seed' });
            }
        }
        if (imported.length === 0) {
            alert('未找到有效的术语对，请检查文件格式');
            return;
        }
        // 合并到现有术语
        const existingKeys = new Set(_terms.map(t => t.en.toLowerCase()));
        let added = 0;
        imported.forEach(t => {
            if (!existingKeys.has(t.en.toLowerCase())) {
                _terms.push(t);
                existingKeys.add(t.en.toLowerCase());
                added++;
            }
        });
        renderTable();
        updateStats();
        alert(`导入完成：新增 ${added} 条，跳过 ${imported.length - added} 条已存在术语`);
    } catch (e) {
        alert('导入失败: ' + e.message);
    }
}

// ---- 初始化记忆库 ----
async function initMemory() {
    const memPath = getMemoryPath();
    if (!memPath) {
        alert('请先配置记忆库路径（在「翻译工作台」输入著作名或在「流水线」中设置路径）');
        return;
    }
    if (!confirm('初始化将重置记忆库，是否继续？')) return;

    try {
        const projectName = $('memoryProjectName')?.textContent || '';
        const result = await pipelineInitMemory(memPath, projectName, null);
        if (result.success) {
            _terms = [];
            renderEmpty('记忆库已初始化，请开始翻译以积累术语');
            _memoryPath = memPath;
            const pathText = $('memoryPathText');
            if (pathText) pathText.textContent = memPath;
        } else {
            alert('初始化失败: ' + (result.error || '未知错误'));
        }
    } catch (e) {
        alert('初始化失败: ' + e.message);
    }
}

// ---- 复制单个术语 ----
function copyTerm(param) {
    if (!param) return;
    const [en, zh] = param.split('|');
    const text = `${en} → ${zh}`;
    navigator.clipboard.writeText(text).then(() => {
        // 简单反馈
        const el = document.querySelector(`[data-param="${param}"]`);
        if (el) {
            const orig = el.textContent;
            el.textContent = '已复制';
            setTimeout(() => { el.textContent = orig; }, 1200);
        }
    }).catch(() => {});
}

// ---- 导出点击处理器 ----
export function getMemoryClickHandlers() {
    return {
        'memory-export':    () => exportTerms(),
        'memory-import':    () => importTerms(),
        'memory-filter':    (el) => setFilter(el.dataset.param),
        'memory-init':      () => initMemory(),
        'memory-copy-term': (el) => copyTerm(el.dataset.param),
    };
}

// ---- 导出变更处理器（搜索输入框） ----
export function setupMemoryListeners() {
    const searchInput = $('memorySearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(onSearch, 200));
    }
    const importFile = $('memoryImportFile');
    if (importFile) {
        importFile.addEventListener('change', (e) => {
            const file = e.target.files?.[0];
            if (file) handleImportFile(file);
            e.target.value = ''; // 重置以支持重复导入
        });
    }
}

// ---- 记忆库面板首次可见时自动加载 ----
export function onMemoryTabVisible() {
    loadMemory();
}
