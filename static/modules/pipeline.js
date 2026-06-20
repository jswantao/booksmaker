// modules/pipeline.js — 翻译流水线面板
import { $, setStatus } from '../dom.js';
import { escapeHtml } from '../utils.js';
import {
    pipelineUpload, pipelineBuildKb, pipelineRun, pipelinePause,
    pipelineResume, pipelineStatus, pipelineResult, pipelineGetMemory,
    pipelineInitMemory, pipelineStitch, pipelineListKbs
} from '../api.js';

// ---- 状态 ----
let _kbName = '';
let _memoryPath = '';
let _pollTimer = null;

// ---- 上传文件 ----
async function uploadFile() {
    const fileInput = $('pipelineFile');
    const file = fileInput?.files?.[0];
    if (!file) {
        setStatus('pipelineUploadStatus', '请先选择文件', 'error');
        return;
    }

    setStatus('pipelineUploadStatus', '上传中...', '');
    const formData = new FormData();
    formData.append('file', file);

    try {
        const result = await pipelineUpload(formData);
        if (result.success) {
            $('pipelineFilePath').value = result.file_path;
            setStatus('pipelineUploadStatus',
                `✅ 上传成功: ${result.file_name} (${(result.chars||0).toLocaleString()} 字符)`, 'success');
            // 自动生成 KB 名称
            if (!$('pipelineKbName').value) {
                const name = file.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9一-鿿_-]/g, '_');
                $('pipelineKbName').value = name;
            }
            // 自动生成记忆库路径
            if (!$('pipelineMemoryPath').value) {
                $('pipelineMemoryPath').value = 'memory/' + file.name.replace(/\.[^.]+$/, '') + '_memory.json';
            }
        } else {
            setStatus('pipelineUploadStatus', '❌ ' + (result.error || '上传失败'), 'error');
        }
    } catch (e) {
        setStatus('pipelineUploadStatus', '❌ 网络错误: ' + e.message, 'error');
    }
}

// ---- 构建知识库 ----
async function buildKb() {
    const filePath = $('pipelineFilePath').value;
    const kbName = $('pipelineKbName').value.trim();

    if (!filePath) {
        setStatus('pipelineBuildStatus', '请先上传文件', 'error');
        return;
    }
    if (!kbName) {
        setStatus('pipelineBuildStatus', '请输入知识库名称', 'error');
        return;
    }

    _kbName = kbName;
    const chunkSize = parseInt($('pipelineChunkSize').value) || 1200;
    const overlap = parseInt($('pipelineOverlap').value) || 150;

    setStatus('pipelineBuildStatus', '⏳ 正在构建知识库（嵌入中...）', '');
    try {
        const result = await pipelineBuildKb(filePath, kbName, chunkSize, overlap);
        if (result.success) {
            setStatus('pipelineBuildStatus',
                `✅ 知识库「${result.kb.name}」构建完成: ${result.kb.chunks} 个片段, ${result.kb.chapters} 个章节`, 'success');
        } else {
            setStatus('pipelineBuildStatus', '❌ ' + (result.error || '构建失败'), 'error');
        }
    } catch (e) {
        setStatus('pipelineBuildStatus', '❌ 请求失败: ' + e.message, 'error');
    }
}

// ---- 运行流水线 ----
async function runPipeline() {
    const filePath = $('pipelineFilePath').value;
    const kbName = $('pipelineKbName').value.trim() || _kbName;

    if (!filePath) {
        setStatus('pipelineRunStatus', '请先上传文件', 'error');
        return;
    }
    if (!kbName) {
        setStatus('pipelineRunStatus', '请先构建或指定知识库名称', 'error');
        return;
    }

    _kbName = kbName;
    _memoryPath = $('pipelineMemoryPath').value.trim() ||
        'memory/' + kbName + '_memory.json';
    const autoSave = parseInt($('pipelineAutoSave').value) || 10;

    setStatus('pipelineRunStatus', '🚀 流水线启动中...', '');
    try {
        const result = await pipelineRun(filePath, kbName, _memoryPath, 0, autoSave);
        if (result.success) {
            setStatus('pipelineRunStatus',
                `✅ 流水线已启动！知识库: ${kbName}`, 'success');
            startPolling();
        } else {
            setStatus('pipelineRunStatus', '❌ ' + (result.error || '启动失败'), 'error');
        }
    } catch (e) {
        setStatus('pipelineRunStatus', '❌ 请求失败: ' + e.message, 'error');
    }
}

// ---- 暂停/恢复 ----
async function doPause() {
    if (!_kbName) return;
    try {
        const result = await pipelinePause(_kbName);
        if (result.success) setStatus('pipelineRunStatus', '⏸ 已暂停', '');
        stopPolling();
    } catch (e) { /* ignore */ }
}

async function doResume() {
    if (!_kbName) return;
    try {
        const result = await pipelineResume(_kbName);
        if (result.success) {
            setStatus('pipelineRunStatus', '▶ 已恢复，继续翻译...', '');
            startPolling();
        }
    } catch (e) { /* ignore */ }
}

// ---- 章节缝合 ----
async function doStitch() {
    if (!_memoryPath) {
        // Try to get it from status
        setStatus('pipelineStitchStatus', '请先运行流水线或指定记忆库路径', 'error');
        return;
    }

    setStatus('pipelineStitchStatus', '🧵 正在执行章节缝合...', '');
    try {
        const result = await pipelineStitch(_memoryPath);
        if (result.success) {
            setStatus('pipelineStitchStatus',
                `✅ 章节缝合完成！终稿保存在: ${result.path}`, 'success');
            if (result.output) {
                const outputEl = $('pipelineOutput');
                if (outputEl) {
                    outputEl.innerHTML = '<pre>' + escapeHtml(
                        result.output.substring(0, 20000)) + '</pre>';
                    if (result.output.length > 20000) {
                        outputEl.innerHTML += '<p style="color:var(--text-muted)">... 输出过长已截断，完整内容请查看文件</p>';
                    }
                }
            }
            stopPolling();
        } else {
            setStatus('pipelineStitchStatus', '❌ ' + (result.error || '缝合失败'), 'error');
        }
    } catch (e) {
        setStatus('pipelineStitchStatus', '❌ 请求失败: ' + e.message, 'error');
    }
}

// ---- 轮询状态 ----
function startPolling() {
    stopPolling();
    _pollTimer = setInterval(refreshStatus, 3000);
    refreshStatus(); // immediate first check
}

function stopPolling() {
    if (_pollTimer) {
        clearInterval(_pollTimer);
        _pollTimer = null;
    }
}

async function refreshStatus() {
    if (!_kbName) return;

    try {
        const result = await pipelineStatus(_kbName);
        if (!result.success) return;

        // 更新进度条
        const total = result.total_chunks || 0;
        const done = result.chunks_done || 0;
        const bar = $('pipelineProgressBar');
        const text = $('pipelineProgressText');
        if (bar) bar.style.width = total > 0 ? (done / total * 100) + '%' : '0%';
        if (text) text.textContent = `${done} / ${total} 段`;

        // 更新状态面板
        const statusEl = $('pipeStatus');
        if (statusEl) {
            if (result.is_done) {
                statusEl.textContent = '✅ 已完成';
                statusEl.style.color = 'var(--status-success-text)';
                stopPolling();
            } else if (result.paused) {
                statusEl.textContent = '⏸ 已暂停';
                statusEl.style.color = 'var(--status-pending-text)';
            } else if (result.running) {
                statusEl.textContent = '🔄 运行中';
                statusEl.style.color = 'var(--accent)';
            } else {
                statusEl.textContent = '⏳ 等待中';
                statusEl.style.color = 'var(--text-secondary)';
            }
        }

        const termsEl = $('pipeTerms');
        if (termsEl) termsEl.textContent = result.terms_count || result.total_terms || 0;

        const chaptersEl = $('pipeChapters');
        if (chaptersEl) chaptersEl.textContent = (result.completed_chapters || []).length;

        const argsEl = $('pipeArgs');
        if (argsEl) argsEl.textContent = result.core_arguments || 0;

        // 尝试获取已完成的结果
        if (result.is_done || (result.running && done > 0)) {
            try {
                const resResult = await pipelineResult(_kbName);
                if (resResult.success && resResult.output) {
                    const outputEl = $('pipelineOutput');
                    if (outputEl && resResult.output.length > 50) {
                        outputEl.innerHTML = '<pre>' + escapeHtml(
                            resResult.output.substring(0, 15000)) + '</pre>';
                    }
                }
            } catch (e) { /* result not ready yet */ }
        }

        // 如果不在运行且没有活跃 pipeline，尝试从记忆库获取状态
        if (!result.running && result.message) {
            try {
                const memPath = _memoryPath || $('pipelineMemoryPath').value.trim();
                if (memPath) {
                    const memResult = await pipelineGetMemory(memPath);
                    if (memResult.success) {
                        const done2 = memResult.chunks_done || 0;
                        const total2 = (memResult.progress || {}).total_chunks || 0;
                        if (bar) bar.style.width = total2 > 0 ? (done2 / total2 * 100) + '%' : '0%';
                        if (text) text.textContent = `${done2} / ${total2} 段`;
                        const termsEl2 = $('pipeTerms');
                        if (termsEl2) termsEl2.textContent = memResult.total_terms || 0;
                        const chaptersEl2 = $('pipeChapters');
                        if (chaptersEl2) chaptersEl2.textContent = (memResult.completed_chapters || []).length;
                    }
                }
            } catch (e) { /* ignore */ }
        }
    } catch (e) {
        // 流水线可能已结束
        stopPolling();
    }
}

// ---- 清空 ----
function clearPipeline() {
    stopPolling();
    _kbName = '';
    _memoryPath = '';
    $('pipelineFilePath').value = '';
    $('pipelineOutput').innerHTML = '<div class="empty-state">上传文件并启动流水线后，翻译结果将在此显示</div>';
    $('pipelineProgressBar').style.width = '0%';
    $('pipelineProgressText').textContent = '0 / 0 段';
    $('pipeStatus').textContent = '待启动';
    $('pipeStatus').style.color = 'var(--text-secondary)';
    $('pipeTerms').textContent = '0';
    $('pipeChapters').textContent = '0';
    $('pipeArgs').textContent = '0';
    setStatus('pipelineUploadStatus', '', '');
    setStatus('pipelineBuildStatus', '', '');
    setStatus('pipelineRunStatus', '', '');
    setStatus('pipelineStitchStatus', '', '');
}

// ---- 导出处理器 ----
export function getPipelineClickHandlers() {
    return {
        'pipeline-upload':         () => uploadFile(),
        'pipeline-build-kb':       () => buildKb(),
        'pipeline-run':            () => runPipeline(),
        'pipeline-pause':          () => doPause(),
        'pipeline-resume':         () => doResume(),
        'pipeline-stitch':         () => doStitch(),
        'pipeline-refresh-status': () => refreshStatus(),
        'pipeline-clear':          () => clearPipeline(),
    };
}
