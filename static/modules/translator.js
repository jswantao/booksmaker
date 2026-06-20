// modules/translator.js — 翻译面板 + 通用提交流程
import { Elements, $ } from '../dom.js';
import { API_PATH } from '../config.js';
import { callTranslate, callGenerateEpub, callReplaceEpub, fetchAPI } from '../api.js';
import { showStatus, setBtnLoading, isBtnLoading, renderEpubOutput } from '../ui.js';
import { escapeHtml, computeHash, adjustInterval } from '../utils.js';
import { AppState } from '../state.js';
import { POLL_CONFIG } from '../config.js';

// ---- RAG 参数 ----
function getSelectedKbGroupId(panel) {
    const sel = document.getElementById(panel + 'GroupSelect');
    return sel ? (sel.dataset.groupId || sel.value || '') : '';
}

function addRagParams(body, panel, selectedKbs) {
    const gid = getSelectedKbGroupId(panel);
    if (gid) body.group_id = gid;
    if (selectedKbs.length > 0) body.kb_ids = selectedKbs;
}

// ---- 翻译任务配置表 ----
const TASK_CONFIGS = {
    translate: {
        statusId:   'translationStatus',
        outputElKey:'translationOutput',
        url:        API_PATH.translate,
        loadingStatus:'翻译中...',
        loadingHtml: '⏳ 正在调用世界史专家...',
        successStatus:'✅ 翻译完成',
        getInputs() {
            return [{ el: $('translateInput'), message: '请输入英文文本' }];
        },
        buildBody(inputs) {
            const useRag = $('translateRag')?.checked ?? true;
            const useTm  = $('translateTm')?.checked ?? true;
            const body = { text: inputs[0].el.value.trim(), use_rag: useRag, use_tm: useTm };
            if (useRag) addRagParams(body, 'translate', AppState.selectedTranslateKbs);
            return body;
        },
        renderSuccess(result) {
            let output = '<pre>' + escapeHtml(result.translation) + '</pre>';
            if (result.from_tm) {
                output += `<div class="tm-match">📖 <span class="label">来自翻译记忆库</span> (使用 ${result.tm_count||1} 次)</div>`;
            } else if (result.tm_references?.length) {
                output += `<div class="tm-match">📖 <span class="label">参考了 ${result.tm_references.length} 条翻译记忆</span></div>`;
            }
            output += `<div class="mt-sm"><button class="btn btn-secondary copy-btn" data-action="copy-output" data-param="translationOutput">📋 复制译文</button></div>`;
            Elements.translationOutput.innerHTML = output;
        },
        onSuccess() { /* trigger TM refresh - handled by caller */ }
    },
    'generate-epub': {
        statusId:   'epubStatus',
        outputElKey:'epubOutput',
        url:        API_PATH.generateEpub,
        loadingStatus:'生成中...',
        loadingHtml: '⏳ 正在生成EPUB代码...',
        successStatus:'✅ EPUB代码生成成功',
        getInputs() {
            return [{ el: $('epubInput'), message: '请输入内容' }];
        },
        buildBody(inputs) {
            const useRag = $('epubRag')?.checked ?? true;
            const body = { content: inputs[0].el.value.trim(), user_epub_code: null, use_rag: useRag };
            if (useRag) addRagParams(body, 'epub', AppState.selectedEpubKbs);
            return body;
        },
        renderSuccess(result) { renderEpubOutput(result, 'epubOutput'); }
    },
    'replace-epub': {
        statusId:   'replaceStatus',
        outputElKey:'replaceOutput',
        url:        API_PATH.replaceEpub,
        loadingStatus:'替换中...',
        loadingHtml: '⏳ 正在替换内容...',
        successStatus:'✅ 替换成功！',
        getInputs() {
            return [
                { el: $('replaceTranslation'), message: '请输入新译文' },
                { el: $('replaceEpubCode'), message: '请粘贴EPUB代码' }
            ];
        },
        buildBody(inputs) {
            return {
                translation: inputs[0].el.value.trim(),
                epub_code: inputs[1].el.value.trim(),
                use_rag: $('epubRag')?.checked ?? true
            };
        },
        renderSuccess(result) { renderEpubOutput(result, 'replaceOutput'); }
    }
};

// ---- 通用提交流程 ----
export async function submitTask(configKey, actionEl) {
    const config = TASK_CONFIGS[configKey];
    if (!config || isBtnLoading(actionEl)) return;

    const inputs = config.getInputs();
    for (const inp of inputs) {
        if (!inp.el.value.trim()) {
            showStatus(config.statusId, inp.message, 'error');
            return;
        }
    }

    setBtnLoading(actionEl, true);
    showStatus(config.statusId, config.loadingStatus, '');
    Elements[config.outputElKey].innerHTML = config.loadingHtml;

    try {
        const body = config.buildBody(inputs);
        // 根据任务类型选择合适的 API 函数
        let result;
        if (configKey === 'translate') result = await callTranslate(body);
        else if (configKey === 'generate-epub') result = await callGenerateEpub(body);
        else result = await callReplaceEpub(body);
        if (result.success) {
            config.renderSuccess(result);
            showStatus(config.statusId, config.successStatus, 'success');
            if (config.onSuccess) config.onSuccess();
        } else {
            showStatus(config.statusId, '❌ ' + result.error, 'error');
            Elements[config.outputElKey].textContent = '错误：' + result.error;
        }
    } catch (e) {
        showStatus(config.statusId, '❌ 请求失败', 'error');
        Elements[config.outputElKey].textContent = '网络错误：' + e.message;
    } finally {
        setBtnLoading(actionEl, false);
    }
}
