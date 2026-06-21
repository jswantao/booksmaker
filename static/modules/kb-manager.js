// modules/kb-manager.js — 知识库管理 + KB 选择器
import { Elements, $ } from '../dom.js';
import { API_PATH, CSS_CLASS } from '../config.js';
import {
    fetchKbList, createKb, updateKb, deleteKbEntry, uploadToKbApi,
    createGroup, updateGroup, deleteGroupEntry, uploadKnowledge,
    listTerms, addTerm, deleteTerm
} from '../api.js';
import { renderKBList, renderKbSelectorTags, populateGroupSelects, showModal, hideModal } from '../ui.js';
import { escapeHtml } from '../utils.js';
import { AppState } from '../state.js';

// ---- KB 管理面板 ----
async function refreshKBManager() {
    try {
        const data = await fetchKbList();
        if (data.success) renderKBList(data.kbs || [], data.groups || []);
    } catch (e) { console.error('refreshKBManager failed', e); }
}

// ---- KB 选择器 ----
export function toggleKbSelector(panel) {
    const checkbox = $(panel === 'translate' ? 'translateRag' : 'epubRag');
    const selector = $(panel + 'KbSelector');
    if (selector) selector.style.display = checkbox?.checked ? 'flex' : 'none';
    if (checkbox?.checked) refreshKbSelectors();
}

export async function refreshKbSelectors() {
    try {
        const data = await fetchKbList();
        if (!data.success) return;
        const kbs = data.kbs || [];
        const groups = data.groups || [];
        ['translate', 'epub'].forEach(panel => {
            populateGroupSelects(panel, groups);
            const selected = panel === 'translate' ? AppState.selectedTranslateKbs : AppState.selectedEpubKbs;
            renderKbSelectorTags(panel, selected, kbs);
        });
    } catch (e) { console.error('refreshKbSelectors failed', e); }
}

export function onGroupSelect(panel) {
    const sel = document.getElementById(panel + 'GroupSelect');
    const gid = sel?.value || '';
    if (panel === 'translate') {
        AppState.selectedTranslateKbs = [];
        if (gid) sel.dataset.groupId = gid;
    } else {
        AppState.selectedEpubKbs = [];
        if (gid) sel.dataset.groupId = gid;
    }
    refreshKbSelectors();
}

// ---- KB 选择器弹窗 ----
async function showKbPicker(panel) {
    try {
        const data = await fetchKbList();
        if (!data.success) return;
        const kbs = data.kbs || [];
        if (!kbs.length) { alert('暂无可用知识库'); return; }

        AppState._kbPickerPanel = panel;
        const selected = panel === 'translate' ? AppState.selectedTranslateKbs : AppState.selectedEpubKbs;
        const currentIds = new Set(selected);

        const listHtml = kbs.map(kb => {
            const checked = currentIds.has(kb.id) ? ' checked' : '';
            return `<label class="kb-pick-item"><input type="checkbox" value="${escapeHtml(kb.id)}"${checked}> ${escapeHtml(kb.name)} <span class="kb-pick-count">(${kb.document_count||0}条)</span></label>`;
        }).join('');

        const listEl = $('kbPickerList');
        if (listEl) listEl.innerHTML = listHtml;
        showModal('kbPickerOverlay');
    } catch (e) { console.error('showKbPicker failed', e); }
}

function hideKbPicker() {
    hideModal('kbPickerOverlay');
    AppState._kbPickerPanel = null;
}

function confirmKbPicker() {
    const checks = document.querySelectorAll('#kbPickerList input[type="checkbox"]');
    const ids = Array.from(checks).filter(c => c.checked).map(c => c.value);
    if (AppState._kbPickerPanel === 'translate') AppState.selectedTranslateKbs = ids;
    else if (AppState._kbPickerPanel === 'epub') AppState.selectedEpubKbs = ids;
    hideKbPicker();
    refreshKbSelectors();
}

function toggleKbPickerAll() {
    const checks = document.querySelectorAll('#kbPickerList input[type="checkbox"]');
    const allChecked = Array.from(checks).every(c => c.checked);
    checks.forEach(c => { c.checked = !allChecked; });
}

function removeKbSelection(panel, kbId) {
    if (panel === 'translate') {
        AppState.selectedTranslateKbs = AppState.selectedTranslateKbs.filter(id => id !== kbId);
    } else {
        AppState.selectedEpubKbs = AppState.selectedEpubKbs.filter(id => id !== kbId);
    }
    refreshKbSelectors();
}

export function getSelectedKbGroupId(panel) {
    const sel = document.getElementById(panel + 'GroupSelect');
    return sel ? (sel.dataset.groupId || sel.value || '') : '';
}

// ---- KB 模态框 ----
function populateGroupSelect(selectId, selectedValue) {
    fetchKbList().then(data => {
        const sel = $(selectId);
        if (!sel) return;
        sel.innerHTML = '<option value="">无分组</option>';
        (data.groups || []).forEach(g => {
            sel.innerHTML += `<option value="${g.id}" ${g.id===selectedValue?'selected':''}>${escapeHtml(g.name)}</option>`;
        });
    }).catch(() => {});
}

function showKbModal(editId, name, desc, embModel, groupId) {
    showModal('kbModalOverlay');
    $('kbModalTitle').textContent = editId ? '编辑知识库' : '新建知识库';
    $('kbModalSaveBtn').textContent = editId ? '保存' : '创建';
    $('kbModalEditId').value = editId || '';
    $('kbModalName').value = name || '';
    $('kbModalDesc').value = desc || '';
    $('kbModalEmbedding').value = embModel || '';
    populateGroupSelect('kbModalGroup', groupId || '');
}

function hideKbModal() { hideModal('kbModalOverlay'); }

async function saveKbModal() {
    const editId = $('kbModalEditId').value;
    const name = $('kbModalName').value.trim();
    const desc = $('kbModalDesc').value.trim();
    const emb = $('kbModalEmbedding').value;
    const gid = $('kbModalGroup').value;
    if (!name) { alert('请输入知识库名称'); return; }
    try {
        let data;
        if (editId) data = await updateKb(editId, { name, description: desc, group_id: gid || null, embedding_model: emb });
        else data = await createKb({ name, description: desc, embedding_model: emb, group_id: gid || null });
        if (data.success) { hideKbModal(); refreshKBManager(); refreshKbSelectors(); }
        else alert('操作失败: ' + data.error);
    } catch (e) { alert('网络错误: ' + e.message); }
}

// ---- 分组模态框 ----
function showGroupModal(editId, name, desc) {
    showModal('groupModalOverlay');
    $('groupModalTitle').textContent = editId ? '编辑分组' : '新建分组';
    $('groupModalSaveBtn').textContent = editId ? '保存' : '创建';
    $('groupModalEditId').value = editId || '';
    $('groupModalName').value = name || '';
    $('groupModalDesc').value = desc || '';
}

function hideGroupModal() { hideModal('groupModalOverlay'); }

async function saveGroupModal() {
    const editId = $('groupModalEditId').value;
    const name = $('groupModalName').value.trim();
    const desc = $('groupModalDesc').value.trim();
    if (!name) { alert('请输入分组名称'); return; }
    try {
        let data;
        if (editId) data = await updateGroup(editId, { name, description: desc });
        else data = await createGroup({ name, description: desc });
        if (data.success) { hideGroupModal(); refreshKBManager(); refreshKbSelectors(); }
        else alert('操作失败: ' + data.error);
    } catch (e) { alert('网络错误: ' + e.message); }
}

// ---- KB 删除/上传 ----
async function deleteKB(kbId) {
    if (!confirm('确定删除此知识库？ChromaDB中的向量数据将一并删除，不可恢复！')) return;
    try {
        const data = await deleteKbEntry(kbId);
        if (data.success) { refreshKBManager(); refreshKbSelectors(); }
        else alert('删除失败: ' + data.error);
    } catch (e) { alert('网络错误: ' + e.message); }
}

async function deleteGroup(groupId) {
    if (!confirm('确定删除此分组？分组内的知识库将变为未分组状态。')) return;
    try {
        const data = await deleteGroupEntry(groupId);
        if (data.success) { refreshKBManager(); refreshKbSelectors(); }
        else alert('删除失败: ' + data.error);
    } catch (e) { alert('网络错误: ' + e.message); }
}

function uploadToKB(kbId) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt,.md';
    input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append('file', file);
        try {
            const data = await uploadToKbApi(kbId, formData);
            if (data.success) { alert('上传成功! ' + data.message); refreshKBManager(); refreshKbSelectors(); }
            else alert('上传失败: ' + data.error);
        } catch (e) { alert('网络错误: ' + e.message); }
    };
    input.click();
}

// ---- 旧版兼容: 知识库上传 ----
async function uploadOldKnowledge(agentName) {
    const inputId = agentName === '世界史专家' ? 'translateKnowledgeFile' : 'epubKnowledgeFile';
    const inputEl = $(inputId);
    const file = inputEl?.files?.[0];
    if (!file) { alert('请选择文件'); return; }
    const formData = new FormData();
    formData.append('file', file);
    formData.append('agent_name', agentName);
    try {
        const data = await uploadKnowledge(agentName, formData);
        if (data.success) { alert('上传成功! ' + data.message); inputEl.value = ''; refreshKBManager(); refreshKbSelectors(); }
        else alert('上传失败: ' + data.error);
    } catch (e) { alert('网络错误: ' + e.message); }
}

// ---- 导出 click 处理器映射 ----
// ---- 术语管理函数 ----
async function refreshTermList(search) {
    try {
        const result = await listTerms(search || '');
        const el = document.getElementById('termList');
        const countEl = document.getElementById('termCount');
        if (!el) return;
        if (!result.success) { el.innerHTML = '<div class="empty-state-sm">加载失败</div>'; return; }
        const entries = Object.entries(result.terms || {});
        if (countEl) countEl.textContent = entries.length + ' 条';
        if (entries.length === 0) { el.innerHTML = '<div class="empty-state-sm">暂无术语，在上方添加</div>'; return; }
        const query = (document.getElementById('termSearchInput')?.value || '').toLowerCase();
        const filtered = query ? entries.filter(([en, zh]) => en.toLowerCase().includes(query) || zh.includes(query)) : entries;
        el.innerHTML = filtered.slice(0, 30).map(([en, zh]) =>
            `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 8px;border-bottom:1px solid var(--border);">
              <span><b>${escapeHtml(en)}</b> → ${escapeHtml(zh)}</span>
              <button class="delete-btn" data-action="delete-term" data-param="${escapeHtml(en)}" data-term="${encodeURIComponent(en)}" style="font-size:0.8rem;padding:2px 8px;">x</button>
            </div>`).join('');
    } catch (e) { console.error(e); }
}

async function addTermHandler() {
    const en = (document.getElementById('termEnInput')?.value || '').trim();
    const zh = (document.getElementById('termZhInput')?.value || '').trim();
    if (!en || !zh) return;
    try { const r = await addTerm(en, zh); if (r.success) { document.getElementById('termEnInput').value = ''; document.getElementById('termZhInput').value = ''; refreshTermList(); } } catch (e) { console.error(e); }
}

async function searchTermHandler() { refreshTermList(document.getElementById('termSearchInput')?.value || ''); }

async function deleteTermHandler(en) {
    try { const r = await deleteTerm(en); if (r.success) refreshTermList(); } catch (e) { console.error(e); }
}

export function getClickHandlers() {
    return {
        'show-kb-modal':         () => showKbModal(),
        'show-group-modal':      () => showGroupModal(),
        'refresh-kb-manager':    () => refreshKBManager(),
        'hide-kb-modal':         () => hideKbModal(),
        'save-kb-modal':         () => saveKbModal(),
        'hide-group-modal':      () => hideGroupModal(),
        'save-group-modal':      () => saveGroupModal(),
        'confirm-kb-picker':     () => confirmKbPicker(),
        'hide-kb-picker':        () => hideKbPicker(),
        'toggle-kb-picker-all':  () => toggleKbPickerAll(),
        'delete-kb':             (el) => deleteKB(el.dataset.param),
        'delete-group':          (el) => deleteGroup(el.dataset.param),
        'upload-kb':             (el) => uploadToKB(el.dataset.param),
        'upload-knowledge':      (el) => uploadOldKnowledge(el.dataset.param),
        'show-kb-picker':        (el) => showKbPicker(el.dataset.param),
        'remove-kb':             (el) => removeKbSelection(el.dataset.panel, el.dataset.kbid),
        'toggle-kb-group':       (el) => el.classList.toggle(CSS_CLASS.collapsed),
        'edit-kb':               (el) => { const p = el.dataset.param.split('|'); showKbModal(p[0], p[1], p[2], p[3], p[4]); },
        'edit-group':            (el) => { const p = el.dataset.param.split('|'); showGroupModal(p[0], p[1], p[2]); },
        'add-term':              () => addTermHandler(),
        'search-term':           () => searchTermHandler(),
        'delete-term':           (el) => deleteTermHandler(decodeURIComponent(el.dataset.term)),
        'none':                  () => {},
    };
}

export function getChangeHandlers() {
    return {
        'toggle-kb-selector': (el) => toggleKbSelector(el.dataset.param),
        'group-select':       (el) => onGroupSelect(el.dataset.param),
    };
}

// Auto-load term list on init
document.addEventListener('DOMContentLoaded', () => { setTimeout(refreshTermList, 500); });


export { refreshKBManager };
