# api/training.py — 模型训练管理 API
"""训练数据导出 / 启动训练 / 进度监控 / 模型管理"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

# 导入统一目录常量
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import MERGED_MODELS_DIR, LEGACY_MODELS_DIR

router = APIRouter()

# ---- 训练状态 ----
_training_state = {
    "running": False,
    "process": None,
    "started_at": None,
    "progress": 0,
    "step": 0,
    "total_steps": 0,
    "loss": None,
    "current_epoch": 0,
    "total_epochs": 0,
    "log_lines": [],
    "error": None,
    "config": {},
    # 增强指标
    "gpu_memory_used": None,
    "gpu_memory_reserved": None,
    "system_ram_used": None,
    "training_speed": None,
    "phase": "idle",
    "loss_history": [],
}
_train_lock = threading.Lock()
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TRAINING_DIR = Path(__file__).resolve().parent.parent.parent / "training"


# ---- 请求模型 ----
class TrainingStartRequest(BaseModel):
    base_model: str = "Qwen/Qwen2-7B-Instruct"
    data_path: str = "data/train.jsonl"
    output_dir: str = "./lora_output"
    epochs: int = 3
    batch_size: int = 1
    gradient_accumulation: int = 8
    learning_rate: float = 2e-4
    max_length: int = 1024
    lora_r: int = 16
    lora_alpha: int = 32
    use_4bit: bool = True
    # 增量训练
    resume_from_lora: str = ""  # 已有 LoRA 适配器路径，留空则从头训练


class ExportRequest(BaseModel):
    tm_db: str = "data/translation_memory.db"
    memory_dir: str = "memory_banks"
    output: str = "data/train.jsonl"


# ---- 端点 ----

@router.get("/api/training/data")
async def training_data_status():
    """检查可用训练数据"""
    tm_path = PROJECT_ROOT / "data" / "translation_memory.db"
    tm_count = 0
    if tm_path.exists():
        import sqlite3
        try:
            conn = sqlite3.connect(str(tm_path))
            tm_count = conn.execute("SELECT COUNT(*) FROM tm_entries").fetchone()[0]
            conn.close()
        except Exception:
            pass

    term_count = 0
    shared_term = PROJECT_ROOT / "memory_banks" / "_shared" / "terminology.json"
    if shared_term.exists():
        try:
            terms = json.loads(shared_term.read_text(encoding="utf-8")).get("terminology", {})
            term_count = len(terms)
        except Exception:
            pass

    memory_books = []
    mb_dir = PROJECT_ROOT / "memory_banks"
    if mb_dir.exists():
        for d in mb_dir.iterdir():
            if d.name.startswith("_"): continue
            mem = d / "memory.json"
            if mem.exists():
                try:
                    data = json.loads(mem.read_text(encoding="utf-8"))
                    memory_books.append({
                        "name": d.name,
                        "terms": len(data.get("terminology", {})),
                        "chunks": len(data.get("translated_chunks", [])),
                    })
                except Exception:
                    pass

    train_file = PROJECT_ROOT / "data" / "train.jsonl"
    train_count = 0
    if train_file.exists():
        train_count = sum(1 for _ in open(str(train_file), encoding="utf-8"))

    return {
        "success": True,
        "tm_entries": tm_count,
        "shared_terms": term_count,
        "memory_books": memory_books,
        "train_file": str(train_file),
        "train_samples": train_count,
        "ready": tm_count > 0 or train_count > 0,
    }


@router.post("/api/training/export")
async def training_export(req: ExportRequest):
    """触发生成训练数据导出"""
    script = TRAINING_DIR / "export_data.py"
    if not script.exists():
        return {"success": False, "error": f"导出脚本未找到: {script}"}

    cmd = [
        sys.executable, str(script),
        "--tm-db", str(PROJECT_ROOT / req.tm_db),
        "--memory-dir", str(PROJECT_ROOT / req.memory_dir),
        "--output", str(PROJECT_ROOT / req.output),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=str(PROJECT_ROOT))
        if result.returncode == 0:
            return {"success": True, "message": result.stdout.strip(), "output_file": req.output}
        else:
            return {"success": False, "error": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "导出超时 (60s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/training/start")
async def training_start(req: TrainingStartRequest):
    """启动微调训练 (后台子进程)。先预下载模型到本地，再启动训练。"""
    global _training_state
    with _train_lock:
        if _training_state["running"]:
            return {"success": False, "error": "已有训练在运行中"}

        script = TRAINING_DIR / "finetune.py"
        if not script.exists():
            return {"success": False, "error": f"训练脚本未找到: {script}"}

        output_dir = str(PROJECT_ROOT / req.output_dir)
        cache_arg = str(PROJECT_ROOT / "model_cache")
        cmd = [
            sys.executable, "-u", str(script),
            "--model", req.base_model,
            "--data", str(PROJECT_ROOT / req.data_path),
            "--output", output_dir,
            "--epochs", str(req.epochs),
            "--batch_size", str(req.batch_size),
            "--gradient_accumulation", str(req.gradient_accumulation),
            "--learning_rate", str(req.learning_rate),
            "--max_seq_length", str(req.max_length),
            "--lora_r", str(req.lora_r),
            "--lora_alpha", str(req.lora_alpha),
            "--cache_dir", cache_arg,
        ]
        # 增量训练：从已有 LoRA 继续
        if req.resume_from_lora:
            lora_path = str(PROJECT_ROOT / req.resume_from_lora) if not os.path.isabs(req.resume_from_lora) else req.resume_from_lora
            cmd.extend(["--resume_from", lora_path])

        _training_state = {
            "running": True,
            "process": None,
            "started_at": datetime.now().isoformat(),
            "progress": 0,
            "step": 0,
            "total_steps": 0,
            "loss": None,
            "current_epoch": 0,
            "total_epochs": req.epochs,
            "log_lines": [f"[TRAIN] 启动训练: {req.base_model}", f"[CACHE] 模型缓存目录: {cache_arg}"],
            "error": None,
            "config": req.model_dump(),
            "gpu_memory_used": None,
            "gpu_memory_reserved": None,
            "system_ram_used": None,
            "training_speed": None,
            "phase": "downloading",
            "loss_history": [],
        }

    def _run():
        nonlocal cmd
        try:
            # 后台预下载模型 — 实际拉取所有文件到本地缓存
            with _train_lock:
                _training_state["log_lines"].append("[CACHE] 预下载模型文件到本地...")
            try:
                cache_dir = str(PROJECT_ROOT / "model_cache")
                # 1) 先尝试 ModelScope SDK 下载
                try:
                    from modelscope import snapshot_download as ms_download
                    ms_id = req.base_model  # ModelScope 上的 ID 与 HF 通常一致
                    _training_state["log_lines"].append(f"[CACHE] ModelScope 下载: {ms_id}")
                    local_path = ms_download(ms_id, cache_dir=os.path.join(cache_dir, ".ms"))
                    _training_state["log_lines"].append(f"[CACHE] ModelScope 完成: {local_path}")
                except Exception as ms_e:
                    _training_state["log_lines"].append(f"[CACHE] ModelScope 失败: {ms_e}")
                    # 2) 回退到 HuggingFace (带镜像)
                    from huggingface_hub import snapshot_download as hf_download
                    _training_state["log_lines"].append(f"[CACHE] HuggingFace 下载: {req.base_model}")
                    local_path = hf_download(
                        req.base_model,
                        cache_dir=os.path.join(cache_dir, ".hf", "hub"),
                        resume_download=True,
                    )
                    _training_state["log_lines"].append(f"[CACHE] HuggingFace 完成: {local_path}")
            except Exception as e:
                err_msg = str(e)[:200]
                with _train_lock:
                    _training_state["log_lines"].append(f"[CACHE] 下载失败: {err_msg}")
                    _training_state["log_lines"].append("[CACHE] 训练脚本将自行尝试下载（可能较慢）")

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["WANDB_DISABLED"] = "true"
            env["WANDB_CONSOLE"] = "off"
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT),
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            with _train_lock:
                _training_state["process"] = proc

            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                with _train_lock:
                    _training_state["log_lines"].append(line)
                    if len(_training_state["log_lines"]) > 200:
                        _training_state["log_lines"] = _training_state["log_lines"][-100:]

                    # ---- 阶段检测 ----
                    ll = line.lower()
                    if any(kw in ll for kw in ("预下载", "modelscope", "huggingface", "snapshot_download", "下载")):
                        if _training_state["phase"] not in ("training", "evaluating", "saving"):
                            _training_state["phase"] = "downloading"
                    elif any(kw in ll for kw in ("加载数据", "📊 加载", "load_and_prepare")):
                        _training_state["phase"] = "loading_data"
                    elif any(kw in ll for kw in ("加载模型", "🤖 加载", "from_pretrained")):
                        _training_state["phase"] = "loading_model"
                    elif any(kw in ll for kw in ("开始 qlora", "开始微调", "开始训练", "🚀", "trainer.train")):
                        _training_state["phase"] = "training"
                    elif any(kw in ll for kw in ("生成测试样本", "评估", "evaluate", "on_evaluate")):
                        _training_state["phase"] = "evaluating"
                    elif any(kw in ll for kw in ("保存", "loRA 权重", "最终模型", "save_pretrained")):
                        if _training_state["phase"] in ("training", "evaluating"):
                            _training_state["phase"] = "saving"

                    # ---- 训练指标解析 ----
                    if "'loss':" in line or "loss=" in line or "loss:" in line:
                        m = re.search(r"loss[=:]\s*([\d.]+)", line)
                        if m:
                            loss_val = float(m.group(1))
                            _training_state["loss"] = loss_val
                            _training_state["loss_history"].append({
                                "step": _training_state["step"],
                                "loss": loss_val,
                                "epoch": _training_state["current_epoch"],
                            })
                            if len(_training_state["loss_history"]) > 500:
                                _training_state["loss_history"] = _training_state["loss_history"][-500:]
                    if "epoch" in line.lower() and "/" in line:
                        m = re.search(r"(\d+)\s*/\s*(\d+)", line)
                        if m:
                            _training_state["current_epoch"] = int(m.group(1))
                            _training_state["total_epochs"] = int(m.group(2))
                    if "Step" in line or "step" in line:
                        m = re.search(r"[Ss]tep[:=]?\s*(\d+)/(\d+)", line)
                        if m:
                            _training_state["step"] = int(m.group(1))
                            _training_state["total_steps"] = int(m.group(2))
                            if _training_state["total_steps"] > 0:
                                _training_state["progress"] = (
                                    _training_state["step"] / _training_state["total_steps"] * 100
                                )

                    # ---- GPU 显存 / 系统内存 / 训练速度 ----
                    m_gpu = re.search(r"GPU 显存: 使用 ([\d.]+)GB,?\s*预留 ([\d.]+)GB", line)
                    if m_gpu:
                        _training_state["gpu_memory_used"] = float(m_gpu.group(1))
                        _training_state["gpu_memory_reserved"] = float(m_gpu.group(2))
                    m_ram = re.search(r"系统内存: 使用 ([\d.]+)GB", line)
                    if m_ram:
                        _training_state["system_ram_used"] = float(m_ram.group(1))
                    m_spd = re.search(r"速度: ([\d.]+)\s*steps/s", line)
                    if m_spd:
                        _training_state["training_speed"] = float(m_spd.group(1))

            proc.wait()
            with _train_lock:
                if proc.returncode == 0:
                    _training_state["phase"] = "complete"
                    _training_state["log_lines"].append("✅ 训练完成")
                    _training_state["progress"] = 100
                else:
                    _training_state["phase"] = "error"
                    last_lines = _training_state["log_lines"][-5:]
                    diag = " | ".join(last_lines) if last_lines else "无日志输出"
                    _training_state["error"] = (
                        f"训练异常退出 (code={proc.returncode})。"
                        f"最后日志: {diag}"
                    )
                    _training_state["log_lines"].append(f"❌ {_training_state['error']}")
                _training_state["running"] = False

                # ---- 持久化训练历史 ----
                try:
                    history_path = PROJECT_ROOT / "data" / "training_history.json"
                    history_path.parent.mkdir(parents=True, exist_ok=True)
                    history = []
                    if history_path.exists():
                        history = json.loads(history_path.read_text(encoding="utf-8"))
                    started = _training_state.get("started_at", "")
                    finished = datetime.now().isoformat()
                    duration = 0
                    if started:
                        try:
                            t0 = datetime.fromisoformat(started)
                            duration = int((datetime.now() - t0).total_seconds())
                        except Exception:
                            pass
                    entry = {
                        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
                        "started_at": started,
                        "finished_at": finished,
                        "base_model": _training_state["config"].get("base_model", ""),
                        "epochs": _training_state["config"].get("epochs", 0),
                        "final_loss": _training_state["loss"],
                        "total_steps": _training_state["total_steps"],
                        "duration_seconds": duration,
                        "status": "completed" if proc.returncode == 0 else "failed",
                        "output_dir": _training_state["config"].get("output_dir", ""),
                    }
                    history.append(entry)
                    with open(history_path, "w", encoding="utf-8") as hf:
                        json.dump(history, hf, ensure_ascii=False, indent=2)
                except Exception:
                    pass
        except FileNotFoundError:
            with _train_lock:
                _training_state["error"] = (
                    f"Python 解释器未找到: {sys.executable}。"
                    f"请确认 Python 已安装且在 PATH 中。"
                )
                _training_state["running"] = False
        except Exception as e:
            with _train_lock:
                _training_state["error"] = f"训练进程异常: {type(e).__name__}: {e}"
                _training_state["running"] = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return {"success": True, "message": "训练已启动", "base_model": req.base_model}


@router.post("/api/training/stop")
async def training_stop():
    """停止训练"""
    with _train_lock:
        if not _training_state["running"]:
            return {"success": False, "error": "没有运行中的训练"}
        proc = _training_state.get("process")
        if proc and proc.poll() is None:
            proc.terminate()
            time.sleep(2)
            if proc.poll() is None:
                proc.kill()
        _training_state["running"] = False
        _training_state["log_lines"].append("⏹ 训练已停止")
    return {"success": True, "message": "训练已停止"}


@router.get("/api/training/status")
async def training_status():
    """获取训练进度"""
    with _train_lock:
        return {
            "success": True,
            "running": _training_state["running"],
            "started_at": _training_state["started_at"],
            "progress": round(_training_state["progress"], 1),
            "step": _training_state["step"],
            "total_steps": _training_state["total_steps"],
            "loss": _training_state["loss"],
            "current_epoch": _training_state["current_epoch"],
            "total_epochs": _training_state["total_epochs"],
            "config": _training_state["config"],
            "error": _training_state["error"],
            # 增强指标
            "gpu_memory_used": _training_state["gpu_memory_used"],
            "gpu_memory_reserved": _training_state["gpu_memory_reserved"],
            "system_ram_used": _training_state["system_ram_used"],
            "training_speed": _training_state["training_speed"],
            "phase": _training_state["phase"],
            "loss_history": _training_state["loss_history"][-100:],
        }


@router.get("/api/training/logs")
async def training_logs(since: int = Query(default=0, description="从第几条开始返回")):
    """获取训练日志 (增量返回)"""
    with _train_lock:
        logs = _training_state["log_lines"]
        new_logs = logs[since:] if since < len(logs) else []
        return {
            "success": True,
            "lines": new_logs,
            "total": len(logs),
            "running": _training_state["running"],
        }


@router.get("/api/training/models")
async def list_trained_models():
    """列出已训练的模型"""
    models = []
    # 扫描合并模型目录（新路径 + 旧路径兼容）
    seen_names = set()
    for models_dir in [Path(MERGED_MODELS_DIR), Path(LEGACY_MODELS_DIR)]:
        if not models_dir.exists():
            continue
        for d in models_dir.iterdir():
            if d.is_dir() and (d / "config.json").exists() and d.name not in seen_names:
                seen_names.add(d.name)
                cfg_file = d / "training_config.json"
                cfg = {}
                if cfg_file.exists():
                    try:
                        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                models.append({
                    "name": d.name,
                    "path": str(d.resolve()),
                    "base_model": cfg.get("base_model", ""),
                    "lora_source": cfg.get("lora_source", ""),
                    "description": cfg.get("description", ""),
                })

    # 也检查 lora 输出目录
    lora_dir = PROJECT_ROOT / "lora_output"
    if lora_dir.exists():
        for d in lora_dir.iterdir():
            if d.is_dir() and (d / "adapter_config.json").exists():
                models.append({
                    "name": f"lora_{d.name}",
                    "path": str(d.resolve()),
                    "type": "lora",
                    "base_model": "",
                    "description": f"LoRA 适配器 ({d.name})",
                })

    return {"success": True, "models": models}


class ParagraphImportRequest(BaseModel):
    pairs: list[dict] = []  # [{原文, 译文}, ...]
    append_to: str = "data/train.jsonl"


@router.post("/api/training/import-paragraphs")
async def import_paragraph_pairs(req: ParagraphImportRequest):
    """从 {原文, 译文} 格式导入段落级翻译对到训练数据"""
    import re

    rows = []
    for pair in req.pairs:
        source = pair.get("原文", pair.get("source", pair.get("input", "")))
        target = pair.get("译文", pair.get("output", pair.get("target", "")))
        if not source or not target:
            continue
        source = re.sub(r"<[^>]+>", "", source).strip()
        target = re.sub(r"<[^>]+>", "", target).strip()
        if len(source) < 20 or len(target) < 10:
            continue
        rows.append({
            "instruction": "将以下历史著作英文段落翻译为学术中文，保持术语一致、风格学术化、准确完整：\n{input}",
            "input": source,
            "output": target,
        })

    # 追加到训练文件
    output_path = PROJECT_ROOT / req.append_to
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return {"success": True, "imported": len(rows), "file": str(output_path)}


@router.post("/api/training/load-seed")
async def load_seed_data():
    """将内置种子训练数据（拜占庭帝国战略历史翻译对）追加到训练文件"""
    seed_path = PROJECT_ROOT / "data" / "seed_train.json"
    if not seed_path.exists():
        return {"success": False, "error": "种子数据文件不存在: data/seed_train.json"}

    try:
        pairs = json.loads(seed_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"success": False, "error": f"种子数据解析失败: {e}"}

    output_path = PROJECT_ROOT / "data" / "train.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    existing = set()
    if output_path.exists():
        for line in open(output_path, encoding="utf-8"):
            if line.strip():
                try:
                    existing.add(json.loads(line.strip()).get("output", "")[:120])
                except Exception:
                    pass

    imported = 0
    with open(output_path, "a", encoding="utf-8") as f:
        for pair in pairs:
            source = pair.get("input", "") or pair.get("原文", "")
            target = pair.get("output", "") or pair.get("译文", "")
            source = re.sub(r"<[^>]+>", "", source).strip()
            target = re.sub(r"<[^>]+>", "", target).strip()
            if len(source) < 20 or len(target) < 10:
                continue
            key = target[:120]
            if key in existing:
                continue
            existing.add(key)
            instruction = pair.get("instruction", "将以下历史著作英文段落翻译为学术中文，保持术语一致、风格学术化、准确完整：")
            row = {"instruction": instruction, "input": source, "output": target}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            imported += 1

    return {"success": True, "imported": imported, "skipped": len(pairs) - imported, "file": str(output_path)}


# ---- 训练环境检查 ----

@router.get("/api/training/check")
async def check_training_env():
    """检查训练依赖是否就绪"""
    deps = {}
    for mod, name in [
        ("torch", "PyTorch"),
        ("transformers", "Transformers"),
        ("peft", "PEFT (LoRA)"),
        ("datasets", "Datasets"),
        ("trl", "TRL (SFTTrainer)"),
        ("bitsandbytes", "BitsAndBytes (4-bit)"),
        ("accelerate", "Accelerate"),
    ]:
        try:
            __import__(mod)
            deps[name] = "ok"
        except ImportError:
            deps[name] = "missing"

    # 检查 GPU
    gpu_available = False
    gpu_info = "未检测到"
    try:
        import torch
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_info = f"{torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_mem // 1024**3}GB)"
    except Exception:
        pass

    all_ok = all(v == "ok" for v in deps.values())

    # 检查常见模型的本地缓存
    cached_models = []
    cache_base = PROJECT_ROOT / "model_cache"
    for scan_dir in [cache_base / ".ms", cache_base / ".hf" / "hub", cache_base]:
        if not scan_dir.is_dir():
            continue
        for child in scan_dir.iterdir():
            if child.is_dir() and (child / "config.json").exists():
                cached_models.append(child.name)

    return {
        "success": True,
        "deps": deps,
        "all_ok": all_ok,
        "gpu_available": gpu_available,
        "gpu_info": gpu_info,
        "python": sys.executable,
        "cached_models": cached_models[:20],
        "cache_dir": str(cache_base),
        "hint": None if all_ok else "pip install -r training/requirements.txt",
    }


# ---- 可用基础模型 ----

RECOMMENDED_MODELS = [
    {"id": "Tencent-Hunyuan/Hy-MT2-1.8B", "label": "Hy-MT2-1.8B (混元翻译 ⭐推荐)"},
    {"id": "Qwen/Qwen3.5-4B", "label": "Qwen3.5-4B (通义最新 4B)"},
    {"id": "Tencent-Hunyuan/Hunyuan-MT-7B", "label": "Hunyuan-MT-7B (混元翻译 7B)"},
    {"id": "Qwen/Qwen2.5-7B-Instruct", "label": "Qwen2.5-7B (通用 7B)"},
    {"id": "Qwen/Qwen2.5-3B-Instruct", "label": "Qwen2.5-3B (轻量)"},
    {"id": "Qwen/Qwen2-7B-Instruct", "label": "Qwen2-7B (通用)"},
    {"id": "Qwen/Qwen2.5-1.5B-Instruct", "label": "Qwen2.5-1.5B (超轻量)"},
]

@router.get("/api/training/available-models")
async def available_base_models():
    """获取所有可用的基础模型（远程推荐 + 本地缓存 + 已合并 + LoRA适配器）"""
    cache_base = PROJECT_ROOT / "model_cache"

    # 1. 本地缓存模型
    cached = []
    recommended_ids = {m["id"] for m in RECOMMENDED_MODELS}
    for scan_dir in [cache_base / ".ms", cache_base / ".hf" / "hub", cache_base]:
        if not scan_dir.is_dir():
            continue
        source = "modelscope" if ".ms" in str(scan_dir) else "huggingface"
        for child in scan_dir.iterdir():
            if not child.is_dir():
                continue
            # ModelScope: org/model_name
            if (child / "config.json").exists():
                model_id = child.name
                if model_id not in recommended_ids:
                    cached.append({"id": model_id, "path": str(child.resolve()), "source": source})
            # HF hub: models--org--name format or org/name
            for sub in child.iterdir() if child.is_dir() else []:
                if sub.is_dir() and (sub / "config.json").exists():
                    model_id = sub.name
                    if model_id not in recommended_ids:
                        cached.append({"id": model_id, "path": str(sub.resolve()), "source": source})

    # 2. 已合并模型 (model_cache/merged/ + 旧 models/ 兼容)
    merged = []
    seen_merged = set()
    for models_dir in [Path(MERGED_MODELS_DIR), Path(LEGACY_MODELS_DIR)]:
        if not models_dir.exists():
            continue
        for d in models_dir.iterdir():
            if d.is_dir() and (d / "config.json").exists() and d.name not in seen_merged:
                seen_merged.add(d.name)
                cfg = {}
                cfg_file = d / "training_config.json"
                if cfg_file.exists():
                    try:
                        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                merged.append({
                    "id": str(d.resolve()),
                    "path": str(d.resolve()),
                    "name": d.name,
                    "base_model": cfg.get("base_model", ""),
                    "description": cfg.get("description", ""),
                })

    # 3. LoRA 适配器 (lora_output/ 目录)
    lora_adapters = []
    lora_dir = PROJECT_ROOT / "lora_output"
    if lora_dir.exists():
        for d in lora_dir.iterdir():
            if d.is_dir() and (d / "adapter_config.json").exists():
                lora_adapters.append({
                    "id": str(d.resolve()),
                    "path": str(d.resolve()),
                    "name": f"lora_{d.name}",
                })

    return {
        "recommended": RECOMMENDED_MODELS,
        "cached": cached,
        "merged": merged,
        "lora_adapters": lora_adapters,
    }


# ---- 训练历史 ----

@router.get("/api/training/history")
async def training_history():
    """获取训练历史记录"""
    history_path = PROJECT_ROOT / "data" / "training_history.json"
    runs = []
    if history_path.exists():
        try:
            runs = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"success": True, "runs": runs}


# ---- 模型合并 ----

class MergeRequest(BaseModel):
    lora_path: str
    base_model: str = "Qwen/Qwen2-7B-Instruct"
    output_name: str = "history-translator"
    strategy: str = "full"

_merge_state = {
    "running": False,
    "process": None,
    "log_lines": [],
    "error": None,
    "done": False,
}
_merge_lock = threading.Lock()


@router.post("/api/training/merge")
async def training_merge(req: MergeRequest):
    """合并 LoRA 适配器到基础模型"""
    global _merge_state
    with _merge_lock:
        if _merge_state["running"]:
            return {"success": False, "error": "已有合并任务在运行中"}

        script = TRAINING_DIR / "merge_and_deploy.py"
        if not script.exists():
            return {"success": False, "error": f"合并脚本未找到: {script}"}

        lora_path = req.lora_path
        if not os.path.isabs(lora_path):
            lora_path = str(PROJECT_ROOT / lora_path)

        output_path = os.path.join(MERGED_MODELS_DIR, req.output_name)
        cache_dir = str(PROJECT_ROOT / "model_cache")

        # 解析基础模型路径：检查 ModelScope / HF 本地缓存
        base_model = req.base_model
        if not os.path.isabs(base_model):
            for candidate in [
                os.path.join(cache_dir, ".ms", base_model.replace("/", os.sep).replace("-", "_").replace(".", "_")),
                os.path.join(cache_dir, ".ms", base_model.replace("/", os.sep)),
            ]:
                if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "config.json")):
                    base_model = candidate
                    break

        cmd = [
            sys.executable, "-u", str(script),
            "--lora", lora_path,
            "--base", base_model,
            "--output", output_path,
            "--strategy", req.strategy,
            "--skip-test",
        ]

        _merge_state = {
            "running": True,
            "process": None,
            "log_lines": [f"[MERGE] 启动合并: {req.lora_path} → {req.output_name}"],
            "error": None,
            "done": False,
        }

    def _run_merge():
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            env["HF_HOME"] = cache_dir
            env["MODELSCOPE_CACHE"] = cache_dir
            env["TRANSFORMERS_CACHE"] = cache_dir
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT),
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            with _merge_lock:
                _merge_state["process"] = proc

            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                with _merge_lock:
                    _merge_state["log_lines"].append(line)
                    if len(_merge_state["log_lines"]) > 200:
                        _merge_state["log_lines"] = _merge_state["log_lines"][-100:]

            proc.wait()
            with _merge_lock:
                if proc.returncode == 0:
                    _merge_state["log_lines"].append("✅ 合并完成")
                    _merge_state["done"] = True
                else:
                    last = _merge_state["log_lines"][-5:]
                    diag = " | ".join(last) if last else "无日志"
                    _merge_state["error"] = f"合并失败 (code={proc.returncode})。{diag}"
                    _merge_state["log_lines"].append(f"❌ {_merge_state['error']}")
                _merge_state["running"] = False
        except Exception as e:
            with _merge_lock:
                _merge_state["error"] = f"合并异常: {type(e).__name__}: {e}"
                _merge_state["running"] = False

    t = threading.Thread(target=_run_merge, daemon=True)
    t.start()
    return {"success": True, "message": "合并已启动"}


@router.get("/api/training/merge/status")
async def merge_status():
    """获取合并进度"""
    with _merge_lock:
        return {
            "success": True,
            "running": _merge_state["running"],
            "log_lines": _merge_state["log_lines"][-50:],
            "error": _merge_state["error"],
            "done": _merge_state["done"],
        }
