# api/training.py — 模型训练管理 API
"""训练数据导出 / 启动训练 / 进度监控 / 模型管理"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

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
    """启动微调训练 (后台子进程)"""
    global _training_state
    with _train_lock:
        if _training_state["running"]:
            return {"success": False, "error": "已有训练在运行中"}

        script = TRAINING_DIR / "finetune.py"
        if not script.exists():
            return {"success": False, "error": f"训练脚本未找到: {script}"}

        output_dir = str(PROJECT_ROOT / req.output_dir)
        cmd = [
            sys.executable, str(script),
            "--model", req.base_model,
            "--data", str(PROJECT_ROOT / req.data_path),
            "--output", output_dir,
            "--epochs", str(req.epochs),
            "--batch_size", str(req.batch_size),
            "--gradient_accumulation", str(req.gradient_accumulation),
            "--learning_rate", str(req.learning_rate),
            "--max_length", str(req.max_length),
            "--lora_r", str(req.lora_r),
            "--lora_alpha", str(req.lora_alpha),
        ]

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
            "log_lines": [f"🚀 启动训练: {req.base_model}"],
            "error": None,
            "config": req.model_dump(),
        }

    def _run():
        nonlocal cmd
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(PROJECT_ROOT),
                encoding="utf-8",
                errors="replace",
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

                    # 解析训练指标
                    if "'loss':" in line or "loss=" in line:
                        import re
                        m = re.search(r"loss[=:]\s*([\d.]+)", line)
                        if m:
                            _training_state["loss"] = float(m.group(1))
                    if "epoch" in line.lower() and "/" in line:
                        import re
                        m = re.search(r"(\d+)\s*/\s*(\d+)", line)
                        if m:
                            _training_state["current_epoch"] = int(m.group(1))
                            _training_state["total_epochs"] = int(m.group(2))
                    if "Step" in line or "step" in line:
                        import re
                        m = re.search(r"[Ss]tep[:=]?\s*(\d+)/(\d+)", line)
                        if m:
                            _training_state["step"] = int(m.group(1))
                            _training_state["total_steps"] = int(m.group(2))
                            if _training_state["total_steps"] > 0:
                                _training_state["progress"] = (
                                    _training_state["step"] / _training_state["total_steps"] * 100
                                )

            proc.wait()
            with _train_lock:
                if proc.returncode == 0:
                    _training_state["log_lines"].append("✅ 训练完成")
                    _training_state["progress"] = 100
                else:
                    _training_state["error"] = f"训练异常退出 (code={proc.returncode})"
                _training_state["running"] = False
        except Exception as e:
            with _train_lock:
                _training_state["error"] = str(e)
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
    models_dir = PROJECT_ROOT / "models"
    if models_dir.exists():
        for d in models_dir.iterdir():
            if d.is_dir() and (d / "config.json").exists():
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

    import re
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
