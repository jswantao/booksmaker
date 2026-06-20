// state.js — 全局应用状态
// 模块职责：跨模块共享的可变状态单例

export const AppState = {
    // KB 选择器状态
    selectedTranslateKbs: [],
    selectedEpubKbs: [],

    // 轮询控制
    tmPollTimer: null,
    kbPollTimer: null,
    tmPollIntervalMs: 10000,
    kbPollIntervalMs: 10000,
    tmLastHash: '',
    kbLastHash: '',

    // KB 选择器面板临时状态
    _kbPickerPanel: null,

    // 按钮加载锁（按 action key 存储）
    _loading: {},
};
