#!/usr/bin/env python
# training/export_data.py — 从 TM + KB 导出训练数据集
"""
数据来源:
  1. 翻译记忆库 (TM) — SQLite 精确匹配对，质量最高
  2. 知识库 (KB) — 如果包含中英对照文档，自动对齐提取
  3. 记忆库 — JSON 术语表可作为术语约束训练样本

输出格式 (JSONL):
  {"instruction": "将以下历史著作英文段落翻译为中文...", "input": "...", "output": "..."}
  {"instruction": "翻译以下术语...", "input": "Treaty of Versailles", "output": "凡尔赛条约"}

用法:
  python training/export_data.py --tm-db data/translation_memory.db --output data/train.jsonl
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

TEMPLATES = {
    "paragraph": "将以下历史著作英文段落翻译为学术中文，保持术语一致、风格统一：\n{input}",
    "term": "翻译以下历史学术术语为中文：\n{input}",
    "sentence": "将以下句子翻译为中文：\n{input}",
}


def export_tm(db_path: str) -> list[dict]:
    """从翻译记忆库导出"""
    rows = []
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute(
            "SELECT source, target FROM tm_entries WHERE source != '' AND target != '' ORDER BY use_count DESC LIMIT 5000"
        )
        for source, target in cur.fetchall():
            source, target = source.strip(), target.strip()
            if not source or not target:
                continue
            # 按长度选择模板
            if len(source) > 200:
                template = TEMPLATES["paragraph"]
            elif len(source) < 60:
                template = TEMPLATES["term"]
            else:
                template = TEMPLATES["sentence"]
            rows.append(
                {"instruction": template.format(input=source), "input": "", "output": target}
            )
        conn.close()
    except Exception as e:
        print(f"[export_tm] {e}")
    return rows


def export_terminology(memory_banks_dir: str) -> list[dict]:
    """从记忆库导出术语"""
    rows = []
    mb_dir = Path(memory_banks_dir)
    if not mb_dir.exists():
        return rows
    for bank_dir in mb_dir.iterdir():
        if bank_dir.name.startswith("_"):
            continue
        mem_file = bank_dir / "memory.json"
        if not mem_file.exists():
            continue
        try:
            data = json.loads(mem_file.read_text(encoding="utf-8"))
            terms = data.get("terminology", {})
            for en, zh in list(terms.items())[:200]:
                rows.append(
                    {
                        "instruction": TEMPLATES["term"].format(input=en),
                        "input": "",
                        "output": zh,
                    }
                )
        except Exception:
            pass
    return rows


def export_shared_terms() -> list[dict]:
    """从共享术语库导出"""
    rows = []
    shared_file = Path("memory_banks/_shared/terminology.json")
    if shared_file.exists():
        try:
            data = json.loads(shared_file.read_text(encoding="utf-8"))
            terms = data.get("terminology", {})
            for en, zh in list(terms.items())[:500]:
                rows.append(
                    {
                        "instruction": TEMPLATES["term"].format(input=en),
                        "input": "",
                        "output": zh,
                    }
                )
        except Exception:
            pass
    return rows


def main():
    parser = argparse.ArgumentParser(description="导出训练数据")
    parser.add_argument("--tm-db", default="data/translation_memory.db")
    parser.add_argument("--memory-dir", default="memory_banks")
    parser.add_argument("--output", default="data/train.jsonl")
    parser.add_argument("--dedup", action="store_true", default=True)
    args = parser.parse_args()

    all_rows = []
    all_rows.extend(export_tm(args.tm_db))
    all_rows.extend(export_terminology(args.memory_dir))
    all_rows.extend(export_shared_terms())

    # 去重
    if args.dedup:
        seen = set()
        unique = []
        for r in all_rows:
            key = (r["instruction"][:80], r["output"][:80])
            if key not in seen:
                seen.add(key)
                unique.append(r)
        all_rows = unique

    # 写入 JSONL
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"✅ 导出 {len(all_rows)} 条训练样本 → {args.output}")
    print(f"   TM:     {sum(1 for r in all_rows if '段落' in r['instruction'])} 段落级")
    print(f"   TM:     {sum(1 for r in all_rows if '句子' in r['instruction'])} 句子级")
    print(f"   术语:   {sum(1 for r in all_rows if '术语' in r['instruction'])} 条")


if __name__ == "__main__":
    main()
