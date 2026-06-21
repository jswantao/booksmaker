// modules/pipeline.js — 翻译流水线面板 v2: KB与源文件分离
import { $, setStatus } from '../dom.js';
import { escapeHtml } from '../utils.js';
import {
    pipelineUpload, pipelineBuildKb, pipelineRun, pipelinePause,
    pipelineResume, pipelineStatus, pipelineResult, pipelineGetMemory,
    pipelineStitch, pipelineListKbs
} from '../api.js';

// ---- 状态 ----
let _pipelineId = '';
let _memoryPath = '';
let _pollTimer = null;

// ---- 上传源文件 ----
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
                `OK 上传成功: ${result.file_name} (${(result.chars||0).toLocaleString()} 字符)`, 'success');
            if (!$('pipelineMemoryPath').value) {
                const name = file.name.replace(/\.[^.]+$/, '');
                $('pipelineMemoryPath').value = 'memory/' + name + '_memory.json';
            }
        } else {
            setStatus('pipelineUploadStatus', 'ERROR: ' + (result.error || '上传失败'), 'error');
        }
    } catch (e) {
        setStatus('pipelineUploadStatus', 'ERROR: ' + e.message, 'error');
    }
}

// ---- 刷新知识库列表 ----
async function refreshKbList() {
    try {
        const result = await pipelineListKbs();
        const sel = $('pipelineKbSelect');
        if (!sel || !result.success) return;
        const kbs = result.kbs || [];
        sel.innerHTML = kbs.length === 0
            ? '<option value="" disabled>暂无知识库，可先在「知识库管理」标签页创建</option>'
            : kbs.map(k => `<option value="${k.id}">${k.name} (${k.document_count||0}条)</option>`).join('');
        setStatus('pipelineKbStatus',
            `共 ${kbs.length} 个知识库可用。按住 Ctrl 多选；不选则无 KB 参考直接翻译`, '');
    } catch (e) {
        setStatus('pipelineKbStatus', '加载知识库列表失败', 'error');
    }
}

// ---- 构建外部知识库（独立功能，使用单独的文件输入） ----
async function buildKb() {
    const kbFileInput = $('pipelineKbFile');
    const kbFile = kbFileInput?.files?.[0];
    const kbName = $('pipelineKbName').value.trim();

    if (!kbFile) {
        // 尝试使用已上传的源文件
        const filePath = $('pipelineFilePath').value;
        if (filePath && kbName) {
            setStatus('pipelineBuildStatus', '正在构建知识库（嵌入中...）', '');
            const chunkSize = parseInt($('pipelineChunkSize').value) || 1200;
            const overlap = parseInt($('pipelineOverlap').value) || 150;
            try {
                const result = await pipelineBuildKb(filePath, kbName, chunkSize, overlap);
                if (result.success) {
                    setStatus('pipelineBuildStatus',
                        `OK 知识库「${result.kb.name}」: ${result.kb.chunks} 片段, ${result.kb.chapters} 章节`, 'success');
                    refreshKbList();
                } else {
                    setStatus('pipelineBuildStatus', 'ERROR: ' + (result.error || '构建失败'), 'error');
                }
            } catch (e) {
                setStatus('pipelineBuildStatus', 'ERROR: ' + e.message, 'error');
            }
        } else {
            setStatus('pipelineBuildStatus', '请选择参考史料文件并输入知识库名称', 'error');
        }
        return;
    }

    if (!kbName) {
        setStatus('pipelineBuildStatus', '请输入知识库名称', 'error');
        return;
    }

    // 先上传 KB 文件
    setStatus('pipelineBuildStatus', '上传史料文件中...', '');
    const formData = new FormData();
    formData.append('file', kbFile);
    try {
        const uploadResult = await pipelineUpload(formData);
        if (!uploadResult.success) {
            setStatus('pipelineBuildStatus', 'ERROR: ' + (uploadResult.error || '上传失败'), 'error');
            return;
        }
        const chunkSize = parseInt($('pipelineChunkSize').value) || 1200;
        const overlap = parseInt($('pipelineOverlap').value) || 150;
        setStatus('pipelineBuildStatus', '正在构建知识库（嵌入中...）', '');
        const result = await pipelineBuildKb(uploadResult.file_path, kbName, chunkSize, overlap);
        if (result.success) {
            setStatus('pipelineBuildStatus',
                `OK 知识库「${result.kb.name}」: ${result.kb.chunks} 片段, ${result.kb.chapters} 章节`, 'success');
            refreshKbList();
        } else {
            setStatus('pipelineBuildStatus', 'ERROR: ' + (result.error || '构建失败'), 'error');
        }
    } catch (e) {
        setStatus('pipelineBuildStatus', 'ERROR: ' + e.message, 'error');
    }
}

// ---- 运行流水线 ----
async function runPipeline() {
    const filePath = $('pipelineFilePath').value;
    if (!filePath) {
        setStatus('pipelineRunStatus', '请先上传待翻译文件', 'error');
        return;
    }

    // 获取选中的 KB IDs
    const kbSel = $('pipelineKbSelect');
    const kbIds = [];
    if (kbSel && kbSel.selectedOptions) {
        for (const opt of kbSel.selectedOptions) {
            if (opt.value) kbIds.push(opt.value);
        }
    }

    _memoryPath = $('pipelineMemoryPath').value.trim() ||
        'memory/' + filePath.replace(/^.*[\\/]/, '').replace(/\.[^.]+$/, '') + '_memory.json';
    _pipelineId = _memoryPath.replace(/^memory[\\/]/, '').replace('_memory.json', '').replace(/[_]/g, '_');
    const autoSave = parseInt($('pipelineAutoSave').value) || 10;

    setStatus('pipelineRunStatus',
        `启动流水线... (KB: ${kbIds.length}个)`, '');
    try {
        const result = await pipelineRun(filePath, kbIds, _memoryPath, 0, autoSave);
        if (result.success) {
            setStatus('pipelineRunStatus',
                `OK 流水线已启动！KB: ${result.kb_count}个`, 'success');
            _pipelineId = result.pipeline_id || _pipelineId;
            startPolling();
        } else {
            setStatus('pipelineRunStatus', 'ERROR: ' + (result.error || '启动失败'), 'error');
        }
    } catch (e) {
        setStatus('pipelineRunStatus', 'ERROR: ' + e.message, 'error');
    }
}

// ---- 暂停/恢复 ----
async function doPause() {
    if (!_pipelineId) return;
    try {
        const result = await pipelinePause(_pipelineId);
        if (result.success) setStatus('pipelineRunStatus', '已暂停', '');
        stopPolling();
    } catch (e) { /* ignore */ }
}

async function doResume() {
    if (!_pipelineId) return;
    try {
        const result = await pipelineResume(_pipelineId);
        if (result.success) {
            setStatus('pipelineRunStatus', '已恢复，继续翻译...', '');
            startPolling();
        }
    } catch (e) { /* ignore */ }
}

// ---- 章节缝合 ----
async function doStitch() {
    if (!_memoryPath) {
        setStatus('pipelineStitchStatus', '请先运行流水线或指定记忆库路径', 'error');
        return;
    }
    setStatus('pipelineStitchStatus', '正在执行章节缝合...', '');
    try {
        const result = await pipelineStitch(_memoryPath);
        if (result.success) {
            setStatus('pipelineStitchStatus',
                `OK 章节缝合完成！终稿: ${result.path}`, 'success');
            if (result.output) {
                const outputEl = $('pipelineOutput');
                if (outputEl) {
                    outputEl.innerHTML = '<pre>' + escapeHtml(result.output.substring(0, 20000)) + '</pre>';
                    if (result.output.length > 20000) {
                        outputEl.innerHTML += '<p style="color:var(--text-muted)">... 输出过长已截断</p>';
                    }
                }
            }
            stopPolling();
        } else {
            setStatus('pipelineStitchStatus', 'ERROR: ' + (result.error || '缝合失败'), 'error');
        }
    } catch (e) {
        setStatus('pipelineStitchStatus', 'ERROR: ' + e.message, 'error');
    }
}

// ---- 轮询 ----
function startPolling() {
    stopPolling();
    _pollTimer = setInterval(refreshStatus, 3000);
    refreshStatus();
}

function stopPolling() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

async function refreshStatus() {
    if (!_pipelineId) return;
    try {
        const result = await pipelineStatus(_pipelineId);
        if (!result.success) return;

        const total = result.total_chunks || 0;
        const done = result.chunks_done || 0;
        const bar = $('pipelineProgressBar');
        const text = $('pipelineProgressText');
        if (bar) bar.style.width = total > 0 ? (done / total * 100) + '%' : '0%';
        if (text) text.textContent = `${done} / ${total} 段`;

        const statusEl = $('pipeStatus');
        if (statusEl) {
            if (result.last_error) {
                statusEl.textContent = 'ERROR: ' + result.last_error;
                statusEl.style.color = 'var(--status-error-text)';
                stopPolling();
            } else if (result.is_done) {
                statusEl.textContent = 'OK 已完成'; statusEl.style.color = 'var(--status-success-text)'; stopPolling();
            } else if (result.paused) { statusEl.textContent = '已暂停'; statusEl.style.color = 'var(--status-pending-text)'; }
            else if (result.running) { statusEl.textContent = '运行中'; statusEl.style.color = 'var(--accent)'; }
            else { statusEl.textContent = '等待中'; statusEl.style.color = 'var(--text-secondary)'; }
        }

        const termsEl = $('pipeTerms');
        if (termsEl) termsEl.textContent = result.terms_count || result.total_terms || 0;
        const chaptersEl = $('pipeChapters');
        if (chaptersEl) chaptersEl.textContent = (result.completed_chapters || []).length;

        // 尝试获取结果
        if (result.is_done || (result.running && done > 0)) {
            try {
                const resResult = await pipelineResult(_pipelineId);
                if (resResult.success && resResult.output) {
                    const outputEl = $('pipelineOutput');
                    if (outputEl && resResult.output.length > 50) {
                        outputEl.innerHTML = '<pre>' + escapeHtml(resResult.output.substring(0, 15000)) + '</pre>';
                    }
                }
            } catch (e) { /* not ready */ }
        }

        // 回退到记忆库状态
        if (!result.running && result.message) {
            try {
                const memPath = _memoryPath || $('pipelineMemoryPath').value.trim();
                if (memPath) {
                    const memResult = await pipelineGetMemory(memPath);
                    if (memResult.success) {
                        const d2 = memResult.chunks_done || 0;
                        const t2 = (memResult.progress || {}).total_chunks || 0;
                        if (bar) bar.style.width = t2 > 0 ? (d2 / t2 * 100) + '%' : '0%';
                        if (text) text.textContent = `${d2} / ${t2} 段`;
                        const te = $('pipeTerms'); if (te) te.textContent = memResult.total_terms || 0;
                        const ce = $('pipeChapters'); if (ce) ce.textContent = (memResult.completed_chapters || []).length;
                    }
                }
            } catch (e) { /* ignore */ }
        }
    } catch (e) { stopPolling(); }
}

// ---- 清空 ----
function clearPipeline() {
    stopPolling();
    _pipelineId = '';
    _memoryPath = '';
    $('pipelineFilePath').value = '';
    $('pipelineOutput').innerHTML = '<div class="empty-state">上传文件并启动流水线后，翻译结果将在此显示</div>';
    $('pipelineProgressBar').style.width = '0%';
    $('pipelineProgressText').textContent = '0 / 0 段';
    $('pipeStatus').textContent = '待启动';
    $('pipeStatus').style.color = 'var(--text-secondary)';
    $('pipeTerms').textContent = '0';
    $('pipeChapters').textContent = '0';
    setStatus('pipelineUploadStatus', '', '');
    setStatus('pipelineBuildStatus', '', '');
    setStatus('pipelineRunStatus', '', '');
    setStatus('pipelineStitchStatus', '', '');
}

// ---- 导出 ----
export function getPipelineClickHandlers() {
    return {
        'pipeline-upload':         () => uploadFile(),
        'pipeline-build-kb':       () => buildKb(),
        'pipeline-run':            () => runPipeline(),
        'pipeline-pause':          () => doPause(),
        'pipeline-resume':         () => doResume(),
        'pipeline-stitch':         () => doStitch(),
        'pipeline-refresh-status': () => refreshStatus(),
        'pipeline-refresh-kbs':    () => refreshKbList(),
        'pipeline-clear':          () => clearPipeline(),
    };
}
