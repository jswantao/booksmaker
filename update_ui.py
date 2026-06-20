import os
import re

# ---- 自动兼容路径 ----
html_path = 'templates/index.html'
if not os.path.exists(html_path):
    html_path = 'booksmaker/templates/index.html'
if not os.path.exists(html_path):
    # 尝试当前脚本所在文件夹下的 templates/index.html
    html_path = os.path.join(os.path.dirname(__file__), 'templates/index.html')
if not os.path.exists(html_path):
    raise FileNotFoundError("无法找到 templates/index.html。请确认本脚本位于项目根目录下。")

new_style = """
        /* ===== 顶级 CSS 变量与现代化设计系统 (Arena.ai 级视觉呈现) ===== */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap');

        :root {
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #0f172a;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            --border: #e2e8f0;
            --border-light: #f1f5f9;
            --input-bg: #ffffff;
            --input-border: #cbd5e1;
            --input-focus: #3b82f6;
            --output-bg: #f1f5f9;
            --tab-bg: #e2e8f0;
            --tab-active-bg: #ffffff;
            --btn-primary: #2563eb;
            --btn-primary-hover: #1d4ed8;
            --btn-secondary: #f1f5f9;
            --btn-secondary-hover: #e2e8f0;
            --btn-success: #10b981;
            --btn-success-hover: #059669;
            --accent: #3b82f6;
            --accent-light: rgba(59, 130, 246, 0.15);
            --shadow: rgba(15, 23, 42, 0.08);
            --shadow-lg: rgba(15, 23, 42, 0.12);
            --status-success-bg: #d1fae5;
            --status-success-text: #065f46;
            --status-pending-bg: #fef3c7;
            --status-pending-text: #92400e;
            --status-error-bg: #fee2e2;
            --status-error-text: #991b1b;
            --tm-match-bg: #f0fdf4;
            --tm-match-border: #10b981;
            --tm-badge-bg: #e0e7ff;
            --tm-badge-color: #3730a3;
            --agent-badge-bg: #f1f5f9;
            --copy-copied-bg: #10b981;
            --copy-copied-text: #ffffff;
            --gradient-from: #2563eb;
            --gradient-to: #7c3aed;
        }

        /* ===== 暗色主题 ===== */
        body.dark {
            --bg: #090d16;
            --card-bg: #111827;
            --text: #f3f4f6;
            --text-secondary: #9ca3af;
            --text-muted: #6b7280;
            --border: #1f2937;
            --border-light: #141f32;
            --input-bg: #1f2937;
            --input-border: #374151;
            --input-focus: #60a5fa;
            --output-bg: #0d131f;
            --tab-bg: #1f2937;
            --tab-active-bg: #374151;
            --btn-primary: #3b82f6;
            --btn-primary-hover: #2563eb;
            --btn-secondary: #1f2937;
            --btn-secondary-hover: #374151;
            --btn-success: #10b981;
            --btn-success-hover: #059669;
            --accent: #60a5fa;
            --accent-light: rgba(96, 165, 250, 0.2);
            --shadow: rgba(0, 0, 0, 0.5);
            --shadow-lg: rgba(0, 0, 0, 0.7);
            --status-success-bg: #064e3b;
            --status-success-text: #6ee7b7;
            --status-pending-bg: #78350f;
            --status-pending-text: #fcd34d;
            --status-error-bg: #7f1d1d;
            --status-error-text: #fca5a5;
            --tm-match-bg: #064e3b;
            --tm-match-border: #10b981;
            --tm-badge-bg: #1e1b4b;
            --tm-badge-color: #818cf8;
            --agent-badge-bg: #1f2937;
            --copy-copied-bg: #059669;
            --copy-copied-text: #ffffff;
            --gradient-from: #60a5fa;
            --gradient-to: #a78bfa;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

        body {
            font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 24px;
            transition: background 0.3s, color 0.3s;
            line-height: 1.6;
        }
        .container { max-width: 1560px; margin: 0 auto; }
        
        .header-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 28px;
        }
        h1 {
            font-size: 2.2rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--gradient-from), var(--gradient-to));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .theme-toggle {
            background: var(--card-bg);
            color: var(--text);
            border: 1px solid var(--border);
            padding: 10px 20px;
            border-radius: 12px;
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: 500;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 2px 8px var(--shadow);
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        .theme-toggle:hover { 
            background: var(--btn-secondary-hover);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px var(--shadow-lg);
        }
        
        /* ===== 主标签栏 ===== */
        .main-tabs {
            display: flex; 
            gap: 8px; 
            margin-bottom: 28px;
            background: var(--tab-bg); 
            padding: 6px; 
            border-radius: 16px;
            max-width: 450px;
            box-shadow: inset 0 2px 4px var(--shadow);
        }
        .main-tabs button {
            flex: 1; 
            padding: 12px 24px; 
            border: none; 
            background: transparent;
            border-radius: 12px; 
            cursor: pointer; 
            font-weight: 600; 
            font-size: 1.05rem;
            color: var(--text-secondary); 
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .main-tabs button.active {
            background: var(--card-bg); 
            color: var(--text); 
            box-shadow: 0 4px 12px var(--shadow-lg);
        }
        .main-tabs button:hover:not(.active) { color: var(--text); }
        
        .maintab-content { display: none; }
        .maintab-content.active { display: block; }

        /* ===== 工作台双栏 ===== */
        .dashboard {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 28px;
        }
        @media (max-width: 1200px) {
            .dashboard { grid-template-columns: 1fr; }
        }

        /* ===== 卡片现代化设计 ===== */
        .card {
            background: var(--card-bg);
            border-radius: 20px;
            padding: 28px;
            box-shadow: 0 8px 30px var(--shadow);
            border: 1px solid var(--border);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            flex-direction: column;
        }
        .card:hover {
            box-shadow: 0 12px 40px var(--shadow-lg);
            border-color: var(--border-light);
        }
        .card h2 {
            font-size: 1.4rem;
            font-weight: 700;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
            letter-spacing: -0.3px;
        }
        .card .subtitle {
            color: var(--text-secondary);
            font-size: 0.95rem;
            margin-bottom: 20px;
        }

        /* ===== 输入与输出框 ===== */
        textarea {
            width: 100%;
            padding: 16px;
            border: 1px solid var(--input-border);
            border-radius: 14px;
            font-family: inherit;
            font-size: 1rem;
            resize: vertical;
            min-height: 140px;
            background: var(--input-bg);
            color: var(--text);
            transition: all 0.2s;
            box-shadow: inset 0 2px 4px var(--shadow);
        }
        textarea:focus {
            outline: none;
            border-color: var(--input-focus);
            box-shadow: 0 0 0 4px var(--accent-light), inset 0 2px 4px var(--shadow);
        }

        .btn {
            background: var(--btn-primary);
            color: white;
            border: none;
            padding: 12px 26px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            display: inline-flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 4px 12px var(--shadow);
        }
        .btn:hover { 
            background: var(--btn-primary-hover); 
            transform: translateY(-1px);
            box-shadow: 0 6px 16px var(--shadow-lg);
        }
        .btn:active { transform: translateY(1px); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; box-shadow: none; }
        
        .btn-success { background: var(--btn-success); }
        .btn-success:hover { background: var(--btn-success-hover); }
        
        .btn-secondary {
            background: var(--btn-secondary);
            color: var(--text);
            box-shadow: 0 2px 6px var(--shadow);
        }
        .btn-secondary:hover { background: var(--btn-secondary-hover); }
        
        .btn-warning { background: #d97706; color: white; }
        .btn-warning:hover { background: #b45309; }
        
        .btn-danger { background: #ef4444; color: white; }
        .btn-danger:hover { background: #dc2626; }
        
        .btn-group {
            display: flex;
            gap: 12px;
            margin-top: 16px;
            flex-wrap: wrap;
        }

        .output-box {
            background: var(--output-bg);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
            margin-top: 16px;
            min-height: 100px;
            white-space: pre-wrap;
            font-size: 0.95rem;
            max-height: 450px;
            overflow-y: auto;
            font-family: 'Fira Code', 'Consolas', monospace;
            box-shadow: inset 0 2px 6px var(--shadow);
            line-height: 1.7;
        }
        .output-box pre {
            white-space: pre-wrap;
            word-break: break-word;
            font-family: inherit;
            color: var(--text);
        }

        .status {
            color: var(--text-secondary);
            font-size: 0.85rem;
            margin-top: 10px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .status.success { color: var(--status-success-text); }
        .status.error { color: var(--status-error-text); }
        .status.info { color: var(--accent); }

        /* ===== API 与智能体配置面板 (无冗余折叠设计) ===== */
        .api-config {
            background: var(--card-bg);
            border-radius: 20px;
            padding: 22px 28px;
            margin-bottom: 28px;
            border: 1px solid var(--border);
            box-shadow: 0 6px 24px var(--shadow);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .api-config:hover {
            box-shadow: 0 10px 32px var(--shadow-lg);
            border-color: var(--border-light);
        }
        .api-config .config-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
        }
        @media (max-width: 800px) {
            .api-config .config-grid { grid-template-columns: 1fr; }
        }
        .api-config .config-grid .full-width { grid-column: 1 / -1; }
        .api-config .config-grid label {
            font-size: 0.9rem;
            font-weight: 500;
            color: var(--text-secondary);
            display: block;
            margin-bottom: 6px;
        }
        .api-config .config-grid input {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid var(--input-border);
            border-radius: 10px;
            font-size: 0.95rem;
            background: var(--input-bg);
            color: var(--text);
            transition: all 0.2s;
        }
        .api-config .config-grid input:focus {
            outline: none;
            border-color: var(--input-focus);
            box-shadow: 0 0 0 4px var(--accent-light);
        }
        .api-config .config-actions {
            display: flex;
            gap: 12px;
            margin-top: 16px;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .config-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
            user-select: none;
        }
        .config-title {
            font-weight: 700;
            font-size: 1.25rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .config-summary-text {
            font-size: 0.9rem;
            color: var(--text-secondary);
            background: var(--btn-secondary);
            padding: 6px 14px;
            border-radius: 20px;
            font-weight: 500;
            display: inline-block;
            border: 1px solid var(--border);
        }
        .config-actions-row {
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
            margin-top: 8px;
        }

        .api-status {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
        }
        .api-status.ready { background: var(--status-success-bg); color: var(--status-success-text); }
        .api-status.pending { background: var(--status-pending-bg); color: var(--status-pending-text); }
        .api-status.error { background: var(--status-error-bg); color: var(--status-error-text); }

        /* ===== 徽章与标签 ===== */
        .agent-badge {
            display: inline-block;
            background: var(--agent-badge-bg);
            padding: 4px 14px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--accent);
            border: 1px solid var(--border);
        }
        .tm-badge {
            display: inline-block;
            background: var(--tm-badge-bg);
            padding: 4px 14px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--tm-badge-color);
        }

        /* ===== 二级选项卡（EPUB切换） ===== */
        .tab-group {
            display: flex;
            gap: 6px;
            margin-bottom: 20px;
            background: var(--tab-bg);
            padding: 6px;
            border-radius: 14px;
        }
        .tab-group button {
            flex: 1;
            padding: 10px 20px;
            border: none;
            background: transparent;
            border-radius: 10px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.95rem;
            color: var(--text-secondary);
            transition: all 0.2s;
        }
        .tab-group button.active {
            background: var(--card-bg);
            color: var(--text);
            box-shadow: 0 2px 8px var(--shadow);
        }
        .tab-group button:hover:not(.active) { color: var(--text); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        /* ===== RAG 与知识库区域 ===== */
        .rag-section {
            margin-top: 24px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
        }
        .rag-section label {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 0.95rem;
            font-weight: 500;
            color: var(--text);
            cursor: pointer;
        }
        .file-upload {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
            margin-top: 12px;
            background: var(--output-bg);
            padding: 12px 16px;
            border-radius: 12px;
            border: 1px dashed var(--border);
        }
        .file-upload input[type="file"] { font-size: 0.9rem; color: var(--text); }
        
        .knowledge-list {
            margin-top: 12px;
            font-size: 0.9rem;
            color: var(--text-secondary);
            max-height: 150px;
            overflow-y: auto;
        }
        .knowledge-list li {
            padding: 8px 12px;
            border-bottom: 1px solid var(--border);
            list-style: none;
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--output-bg);
            margin-bottom: 4px;
            border-radius: 8px;
        }

        /* ===== 翻译记忆库底部管理面板 ===== */
        .panel-card {
            margin-top: 28px;
            background: var(--card-bg);
            border-radius: 20px;
            padding: 28px;
            border: 1px solid var(--border);
            box-shadow: 0 8px 30px var(--shadow);
        }
        .panel-card-sm {
            margin-top: 28px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
            flex-wrap: wrap;
            background: var(--card-bg);
            border-radius: 20px;
            padding: 20px 28px;
            border: 1px solid var(--border);
            box-shadow: 0 4px 20px var(--shadow);
        }
        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 20px;
        }
        .panel-subtitle {
            font-size: 0.95rem;
            color: var(--text-secondary);
            margin-top: 4px;
        }
        .panel-actions {
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        
        .add-pair-section {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid var(--border);
        }
        .add-pair-grid {
            display: grid;
            grid-template-columns: 1fr 1fr auto;
            gap: 12px;
            margin-top: 8px;
        }
        .text-input {
            padding: 10px 16px;
            border: 1px solid var(--input-border);
            border-radius: 10px;
            background: var(--input-bg);
            color: var(--text);
            font-size: 0.95rem;
            transition: all 0.2s;
        }
        .text-input:focus {
            outline: none;
            border-color: var(--input-focus);
            box-shadow: 0 0 0 4px var(--accent-light);
        }
        .search-input { width: 240px; }
        
        .tm-list { 
            max-height: 350px; 
            overflow-y: auto; 
            border: 1px solid var(--border);
            border-radius: 14px;
            divide-y: 1px solid var(--border);
        }
        .tm-item {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            font-size: 0.95rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--output-bg);
        }
        .tm-item:last-child { border-bottom: none; }
        .tm-item .source { font-weight: 500; color: var(--text); flex: 1; }
        .tm-item .target { color: var(--btn-success); font-weight: 600; flex: 1; margin: 0 16px; }
        .tm-item .count { color: var(--text-muted); font-size: 0.85rem; margin-right: 16px; }
        .tm-item .delete-btn {
            background: var(--card-bg);
            border: 1px solid var(--border);
            padding: 6px 12px;
            border-radius: 8px;
            color: #ef4444;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 500;
            transition: all 0.2s;
        }
        .tm-item .delete-btn:hover { background: #fee2e2; border-color: #ef4444; }

        /* ===== KB 管理面板 ===== */
        .kb-toolbar { display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
        .kb-group-header {
            display: flex; align-items: center; justify-content: space-between;
            padding: 16px 20px;
            background: var(--output-bg); border-radius: 14px; margin-bottom: 12px;
            font-weight: 600; font-size: 1.05rem; cursor: pointer;
            border: 1px solid var(--border);
            transition: all 0.2s;
        }
        .kb-group-header:hover { border-color: var(--accent); }
        .kb-group-header .expand-icon { transition: transform 0.2s; margin-right: 10px; }
        .kb-group-header.collapsed .expand-icon { transform: rotate(-90deg); }
        .kb-group-header.collapsed + .kb-items { display: none; }
        .kb-items { margin-left: 24px; margin-bottom: 20px; }
        .kb-item {
            display: flex; align-items: center; justify-content: space-between;
            gap: 16px; padding: 14px 20px;
            background: var(--card-bg);
            border: 1px solid var(--border); border-radius: 12px; margin-bottom: 8px;
            box-shadow: 0 2px 8px var(--shadow);
            transition: all 0.2s;
        }
        .kb-item:hover { border-color: var(--accent); box-shadow: 0 4px 12px var(--shadow-lg); }
        .kb-item .kb-info { flex: 1; }
        .kb-item .kb-name { font-weight: 700; font-size: 1rem; color: var(--text); }
        .kb-item .kb-meta { font-size: 0.85rem; color: var(--text-secondary); margin-top: 4px; }
        .kb-actions { display: flex; gap: 8px; }
        .kb-actions button, .grp-actions button {
            font-size: 0.85rem; font-weight: 500; padding: 6px 14px; border: 1px solid var(--border);
            border-radius: 8px; background: var(--btn-secondary); color: var(--text);
            cursor: pointer; transition: all 0.2s;
        }
        .kb-actions button:hover, .grp-actions button:hover { background: var(--card-bg); border-color: var(--accent); }
        .kb-actions .btn-del:hover { background: #fee2e2; color: #dc2626; border-color: #ef4444; }

        /* ===== KB 选择器 ===== */
        .kb-selector {
            display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-top: 10px;
        }
        .kb-selector select {
            padding: 8px 14px; border: 1px solid var(--input-border); border-radius: 10px;
            font-size: 0.9rem; background: var(--input-bg); color: var(--text); min-width: 180px;
            font-weight: 500;
        }
        .kb-selector .selected-tags { display: flex; gap: 6px; flex-wrap: wrap; }
        .kb-selector .kb-tag {
            display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px;
            background: var(--tm-badge-bg); color: var(--tm-badge-color);
            border-radius: 14px; font-size: 0.85rem; font-weight: 600; cursor: pointer;
            border: 1px solid var(--border);
        }

        /* ===== 模态框 ===== */
        .modal-overlay {
            position: fixed; inset: 0; background: rgba(0,0,0,0.6);
            backdrop-filter: blur(4px);
            display: flex; align-items: center; justify-content: center; z-index: 1000;
            animation: fadeIn 0.2s ease-out;
        }
        .modal-overlay.hidden { display: none; }
        .modal {
            background: var(--card-bg); border-radius: 24px; padding: 36px;
            max-width: 560px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            border: 1px solid var(--border);
            animation: modalPop 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .modal h3 { margin-bottom: 20px; font-size: 1.4rem; font-weight: 700; }
        .modal label { display: block; font-size: 0.95rem; font-weight: 600; color: var(--text-secondary); margin: 16px 0 6px; }
        .modal input, .modal select, .modal textarea {
            width: 100%; padding: 12px 16px; border: 1px solid var(--input-border);
            border-radius: 12px; font-size: 0.95rem; background: var(--input-bg); color: var(--text);
        }
        .modal .modal-actions { display: flex; gap: 12px; margin-top: 28px; justify-content: flex-end; }

        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes modalPop { from { transform: scale(0.95) translateY(10px); opacity: 0; } to { transform: scale(1) translateY(0); opacity: 1; } }

        .example-btn {
            font-size: 0.85rem;
            font-weight: 600;
            padding: 6px 14px;
            background: var(--btn-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            cursor: pointer;
            color: var(--accent);
            transition: all 0.2s;
        }
        .example-btn:hover { background: var(--card-bg); border-color: var(--accent); }
        .full-width-card { grid-column: 1 / -1; }
        
        .tm-match {
            background: var(--tm-match-bg);
            border-left: 4px solid var(--tm-match-border);
            padding: 12px 16px;
            margin-top: 12px;
            border-radius: 8px;
            font-size: 0.95rem;
            box-shadow: 0 2px 6px var(--shadow);
        }
        .tm-match .label { color: var(--tm-match-border); font-weight: 700; margin-bottom: 4px; display: block; }
        
        .checkbox-group {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            margin: 14px 0;
            background: var(--output-bg);
            padding: 10px 16px;
            border-radius: 12px;
            border: 1px solid var(--border);
        }
        .checkbox-group label {
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text);
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
        }
        
        .copy-btn {
            font-size: 0.85rem;
            font-weight: 600;
            padding: 6px 16px;
            background: var(--btn-secondary);
            border: 1px solid var(--border);
            border-radius: 8px;
            cursor: pointer;
            color: var(--text-secondary);
            transition: all 0.2s;
        }
        .copy-btn:hover { background: var(--card-bg); color: var(--text); border-color: var(--accent); }
        .copy-btn.copied { background: var(--copy-copied-bg); color: var(--copy-copied-text); border-color: var(--copy-copied-bg); }

        /* ===== 工具类 ===== */
        .empty-state {
            color: var(--text-muted);
            text-align: center;
            padding: 40px 20px;
            font-size: 1rem;
            font-weight: 500;
        }
        .empty-state-sm { color: var(--text-muted); font-size: 0.9rem; padding: 12px; text-align: center; }
        .kb-count { font-size: 0.85rem; color: var(--text-secondary); font-weight: 600; }
        .kb-default-hint { font-size: 0.8rem; color: var(--accent); font-weight: 600; background: var(--accent-light); padding: 2px 8px; border-radius: 6px; }
        .kb-select-btn { font-size: 0.8rem; padding: 4px 10px; }
        .ungrouped-header { font-weight: 700; font-size: 1rem; margin-bottom: 8px; color: var(--text-secondary); }
        .config-status-msg { font-size: 0.9rem; font-weight: 500; margin-left: 12px; }
        .config-status-msg.success { color: var(--status-success-text); }
        .config-status-msg.error { color: var(--status-error-text); }
        .config-status-msg.pending { color: var(--status-pending-text); }
        .config-status-msg.muted { color: var(--text-muted); }
        
        .bge-status, .llm-status {
            display: none;
            grid-column: 1 / -1;
            margin-top: 8px;
            font-size: 0.9rem;
            background: var(--output-bg);
            padding: 10px 16px;
            border-radius: 10px;
            border: 1px solid var(--border);
        }
        .config-select {
            width: 100%; padding: 12px 16px; border: 1px solid var(--input-border);
            border-radius: 10px; font-size: 0.95rem; background: var(--input-bg);
            color: var(--text); font-weight: 500; transition: all 0.2s;
        }
        .config-select:focus { outline: none; border-color: var(--input-focus); box-shadow: 0 0 0 4px var(--accent-light); }
        .section-label, .section-label-inline { font-size: 0.9rem; font-weight: 600; color: var(--text-secondary); }
        .mt-sm { margin-top: 8px; } .mt-md { margin-top: 16px; } .mb-sm { margin-bottom: 8px; }
        
        /* KB 选择器模态框 */
        .kb-pick-item {
            display: flex; align-items: center; justify-content: space-between;
            padding: 12px 16px; border-radius: 10px; cursor: pointer;
            font-size: 0.95rem; color: var(--text); border: 1px solid var(--border);
            margin-bottom: 6px; transition: all 0.2s; background: var(--output-bg);
        }
        .kb-pick-item:hover { border-color: var(--accent); background: var(--card-bg); box-shadow: 0 2px 8px var(--shadow); }
        .kb-pick-count { font-size: 0.85rem; font-weight: 600; color: var(--accent); background: var(--accent-light); padding: 2px 8px; border-radius: 6px; }
        .kb-pick-list { max-height: 350px; overflow-y: auto; margin: 16px 0; }
        .kb-picker-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .kb-picker-header h3 { margin: 0; font-size: 1.2rem; }
"""

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace style
content = re.sub(r'<style>.*?</style>', '<style>' + new_style + '</style>', content, flags=re.DOTALL)

# Update apiConfig block in HTML
old_api_config = r'<div class="api-config" id="apiConfig">.*?<div class="dashboard">'
new_api_config = """<div class="api-config" id="apiConfig">
        <div class="config-header" data-action="toggle-api-config" style="cursor:pointer;" title="点击展开/收起配置面板">
            <div style="display:flex; align-items:center; flex-wrap:wrap; gap:12px;">
                <span class="config-title">⚙️ 智能体与环境配置</span>
                <span id="apiStatusBadge" class="api-status pending">⏳ 未配置</span>
                <span id="configSummaryText" class="config-summary-text">⚡ 当前驱动：未配置</span>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" id="apiConfigToggleBtn" onclick="event.stopPropagation()">收起面板 ⬆️</button>
        </div>
        <div class="config-grid" id="apiConfigGrid">
            <div class="full-width">
                <label>API Key <span class="required-mark">*</span></label>
                <input type="password" id="apiKey" placeholder="sk-... 输入您的API密钥">
            </div>
            <div>
                <label>API Base URL</label>
                <input type="text" id="apiBaseUrl" placeholder="https://api.openai.com/v1" value="https://api.openai.com/v1">
            </div>
            <div>
                <label>LLM 提供者</label>
                <select id="llmProvider" data-change="llm-provider" class="config-select">
                    <option value="openai">OpenAI API</option>
                    <option value="local">本地模型 (Qwen2.5-1.5B)</option>
                </select>
            </div>
            <div id="openaiModelGroup">
                <label>模型名称</label>
                <input type="text" id="apiModel" placeholder="gpt-4-turbo-preview" value="gpt-4-turbo-preview">
            </div>
            <div id="localModelConfig" style="display:none;">
                <label>本地翻译模型</label>
                <input type="text" id="localTranslateModel" placeholder="Qwen/Qwen2.5-1.5B-Instruct" value="Qwen/Qwen2.5-1.5B-Instruct">
                <label style="margin-top:10px;">本地 EPUB 模型（留空则复用翻译模型）</label>
                <input type="text" id="localEpubModel" placeholder="留空 = 复用翻译模型">
            </div>
            <div id="llmStatus" class="llm-status" style="display:none; grid-column:1/-1;">
                <span id="llmStatusText" style="color:var(--text-secondary); font-weight:500;"></span>
            </div>
            <div>
                <label>Embedding 提供者</label>
                <select id="embeddingProvider" data-change="embedding-provider" class="config-select">
                    <option value="openai">OpenAI API</option>
                    <option value="bge">BGE 本地模型 (BAAI/bge-base-zh-v1.5)</option>
                </select>
            </div>
            <div id="openaiEmbeddingGroup">
                <label>OpenAI Embedding 模型</label>
                <input type="text" id="apiEmbedding" placeholder="text-embedding-ada-002" value="text-embedding-ada-002">
            </div>
            <div id="bgeStatus" class="bge-status" style="grid-column:1/-1;">
                <span id="bgeStatusText" style="font-weight:500;"></span>
                <span id="bgeStatusSpinner" style="display:none;"> ⏳</span>
            </div>
            <div class="full-width config-actions-row" style="margin-top:20px; padding-top:16px; border-top:1px solid var(--border); justify-content:flex-end;">
                <span id="configStatus" class="config-status-msg muted" style="margin-right:auto;"></span>
                <button type="button" class="btn btn-secondary" data-action="clear-config">重置配置</button>
                <button type="button" class="btn btn-success" data-action="save-config">💾 保存并测试</button>
            </div>
        </div>
    </div>

    <div class="dashboard">"""

content = re.sub(old_api_config, new_api_config, content, flags=re.DOTALL)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully updated index.html UI!")
