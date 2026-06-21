// api.js — API 通信层
// 模块职责：封装所有 HTTP 请求，统一错误处理
import { API_PATH } from './config.js';

/**
 * 基础 POST JSON 请求
 */
export async function fetchAPI(url, data) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!resp.ok) {
        let errMsg = 'HTTP ' + resp.status;
        try { const ed = await resp.json(); errMsg = ed.detail || ed.error || errMsg; } catch (_) { /* ignore */ }
        throw new Error(errMsg);
    }
    return await resp.json();
}

/**
 * 通用 GET 请求
 */
export async function fetchGET(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return await resp.json();
}

/**
 * 通用 DELETE 请求
 */
export async function fetchDELETE(url) {
    const resp = await fetch(url, { method: 'DELETE' });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return await resp.json();
}

// ---- 配置 API ----
export function saveConfig(body) {
    return fetch(API_PATH.config, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    }).then(r => r.json());
}

export function loadConfig() {
    return fetchGET(API_PATH.config);
}

export function clearConfig(body) {
    return fetch(API_PATH.config, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
}

export function fetchEmbeddingStatus() {
    return fetchGET(API_PATH.embeddingStatus);
}

export function fetchLlmStatus() {
    return fetchGET(API_PATH.llmStatus);
}

// ---- 翻译 & EPUB API ----
export function callTranslate(body) {
    return fetchAPI(API_PATH.translate, body);
}

export function callEpubReplace(body) {
    return fetchAPI(API_PATH.epubReplace, body);
}

// ---- 翻译记忆 API ----
export function fetchTmList() {
    return fetchGET(API_PATH.tmList + '?limit=100');
}

export function deleteTmEntry(id) {
    return fetchDELETE(API_PATH.tmList + '/' + id);
}

export function clearTmAll() {
    return fetchDELETE(API_PATH.tmClear);
}

export function addTmPair(source, target) {
    return fetchAPI(API_PATH.tmAdd, { source, target });
}

// ---- 知识库 API ----
export function fetchKbList() {
    return fetchGET(API_PATH.kb);
}

export function createKb(body) {
    return fetchAPI(API_PATH.kb, body);
}

export function updateKb(id, body) {
    return fetch(API_PATH.kb + '/' + id, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    }).then(r => r.json());
}

export function deleteKbEntry(id) {
    return fetchDELETE(API_PATH.kb + '/' + id);
}

export function uploadToKbApi(kbId, formData) {
    return fetch(API_PATH.kb + '/' + kbId + '/upload', {
        method: 'POST',
        body: formData
    }).then(r => r.json());
}

// ---- KB 分组 API ----
export function createGroup(body) {
    return fetchAPI(API_PATH.kbGroups, body);
}

export function updateGroup(id, body) {
    return fetch(API_PATH.kbGroups + '/' + id, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    }).then(r => r.json());
}

export function deleteGroupEntry(id) {
    return fetchDELETE(API_PATH.kbGroups + '/' + id);
}

// ---- 知识库文档 API ----
export function fetchKnowledge() {
    return fetchGET(API_PATH.knowledge);
}

export function uploadKnowledge(agentName, formData) {
    return fetch(API_PATH.knowledgeUpload, {
        method: 'POST',
        body: formData
    }).then(r => r.json());
}

// ---- Pipeline API ----
export function pipelineUpload(formData) {
    return fetch(API_PATH.pipelineUpload, {
        method: 'POST',
        body: formData
    }).then(r => r.json());
}

export function pipelineBuildKb(filePath, kbName, chunkSize, overlap) {
    return fetchAPI(API_PATH.pipelineBuildKb, {
        file_path: filePath, kb_name: kbName,
        chunk_size: chunkSize || 1200, overlap: overlap || 150
    });
}

export function pipelineRun(filePath, kbIds, memoryPath, resumeFrom, autoSaveInterval) {
    return fetchAPI(API_PATH.pipelineRun, {
        file_path: filePath, kb_ids: kbIds || [],
        memory_path: memoryPath || '',
        resume_from: resumeFrom || 0,
        auto_save_interval: autoSaveInterval || 10
    });
}

export function pipelinePause(kbName) {
    return fetchAPI(API_PATH.pipelinePause + '/' + encodeURIComponent(kbName), {});
}

export function pipelineResume(kbName) {
    return fetchAPI(API_PATH.pipelineResume + '/' + encodeURIComponent(kbName), {});
}

export function pipelineStatus(kbName) {
    return fetchGET(API_PATH.pipelineStatus + '/' + encodeURIComponent(kbName));
}

export function pipelineResult(kbName) {
    return fetchGET(API_PATH.pipelineResult + '/' + encodeURIComponent(kbName));
}

export function pipelineGetMemory(memoryPath) {
    return fetchGET(API_PATH.pipelineMemory + '/' + encodeURIComponent(memoryPath));
}

export function pipelineInitMemory(memoryPath, project, terminology) {
    return fetchAPI(API_PATH.pipelineMemoryInit, {
        memory_path: memoryPath, project: project || '',
        terminology: terminology || null
    });
}

export function pipelineStitch(memoryPath) {
    return fetchAPI(API_PATH.pipelineStitch, { memory_path: memoryPath });
}

export function pipelineListKbs() {
    return fetchGET(API_PATH.pipelineKbs);
}

// ---- 术语知识库 API ----
export function listTerms(search) {
    const url = API_PATH.terminology + (search ? '?search=' + encodeURIComponent(search) : '');
    return fetchGET(url);
}

export function addTerm(enTerm, zhTerm) {
    return fetchAPI(API_PATH.terminology, { en_term: enTerm, zh_term: zhTerm });
}

export function deleteTerm(enTerm) {
    return fetchDELETE(API_PATH.terminology + '/' + encodeURIComponent(enTerm));
}
