#!/usr/bin/env python
# training/finetune.py — QLoRA 微调历史著作翻译模型
"""
QLoRA (Quantized Low-Rank Adaptation) — 在 4-bit 量化模型上训练低秩适配器

显存需求:
  - 7B 模型: ~8GB (batch_size=1, gradient_checkpointing)
  - 1.5B 模型: ~4GB

输出:
  - ./lora_output/  — LoRA 适配器权重 (约 20-50MB)
  - ./lora_output/checkpoint-*/ — 各 checkpoint

用法:
  python training/finetune.py \
    --model Qwen/Qwen2-7B-Instruct \
    --data data/train.jsonl \
    --output ./lora_output \
    --epochs 3

训练完成后，用 merge_and_deploy.py 合并权重。
"""

import argparse
import json
import os
from pathlib import Path

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments,
    DataCollatorForSeq2Seq,
)
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from trl import SFTTrainer


def load_dataset(data_path: str) -> Dataset:
    """加载 JSONL 训练数据并转换为 HuggingFace Dataset"""
    data = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return Dataset.from_list(data)


def format_prompt(example: dict) -> str:
    """格式化为 Qwen/ChatML 对话格式"""
    instruction = example.get("instruction", "翻译以下文本为中文")
    input_text = example.get("input", "")
    output = example.get("output", "")

    # ChatML 格式
    system = "你是一位精通历史学术著作翻译的专家。翻译时保持术语一致、风格学术化、准确完整。"
    user_content = f"{instruction}"
    if input_text:
        user_content += f"\n\n{input_text}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": output},
    ]

    # 构建 ChatML prompt
    parts = []
    for msg in messages:
        parts.append(f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="QLoRA 微调翻译模型")
    parser.add_argument("--model", default="Qwen/Qwen2-7B-Instruct", help="基础模型")
    parser.add_argument("--data", default="data/train.jsonl", help="训练数据 JSONL")
    parser.add_argument("--output", default="./lora_output", help="LoRA 输出目录")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--gradient_accumulation", type=int, default=8)
    parser.add_argument("--learning_rate", type=float, default=2e-4)
    parser.add_argument("--max_length", type=int, default=1024)
    parser.add_argument("--lora_r", type=int, default=16, help="LoRA rank")
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--use_wandb", action="store_true", help="启用 WandB 日志")
    parser.add_argument("--resume_from", default=None, help="从 checkpoint 恢复")
    args = parser.parse_args()

    if not args.use_wandb:
        os.environ["WANDB_DISABLED"] = "true"

    # ---- 加载数据集 ----
    print(f"📂 加载数据: {args.data}")
    dataset = load_dataset(args.data)
    print(f"   样本数: {len(dataset)}")

    # 分割训练/验证 (90/10)
    split = dataset.train_test_split(test_size=0.1, seed=42)
    train_ds = split["train"]
    val_ds = split["test"]
    print(f"   训练集: {len(train_ds)}, 验证集: {len(val_ds)}")

    # ---- 4-bit 量化配置 ----
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )

    # ---- 加载模型 ----
    print(f"📦 加载基础模型: {args.model}")
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        attn_implementation="sdpa",
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # ---- 准备 LoRA ----
    model = prepare_model_for_kbit_training(model)

    # 检测模型架构，选择合适的 target_modules
    model_type = model.config.model_type
    if "qwen" in model_type.lower():
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    elif "llama" in model_type.lower():
        target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    else:
        # 自动查找所有 Linear 层
        from transformers.pytorch_utils import find_all_linear_names
        target_modules = find_all_linear_names(model)

    print(f"   LoRA target_modules: {target_modules}")

    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=target_modules,
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # ---- 训练参数 ----
    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        learning_rate=args.learning_rate,
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        logging_steps=10,
        save_steps=200,
        eval_steps=200,
        save_total_limit=3,
        evaluation_strategy="steps",
        save_strategy="steps",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        fp16=torch.cuda.is_available(),
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
        report_to="wandb" if args.use_wandb else "none",
        remove_unused_columns=False,
        dataloader_pin_memory=False,
    )

    # ---- 数据格式化 ----
    def formatting_func(example):
        return format_prompt(example)

    # ---- 训练 ----
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        formatting_func=formatting_func,
        data_collator=DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model, padding=True),
    )

    print(f"\n🚀 开始训练 (epochs={args.epochs}, lr={args.learning_rate}, batch={args.batch_size}×{args.gradient_accumulation})")
    trainer.train(resume_from_checkpoint=args.resume_from)

    # ---- 保存最终模型 ----
    final_path = Path(args.output) / "final"
    trainer.model.save_pretrained(final_path)
    tokenizer.save_pretrained(final_path)
    print(f"\n✅ 训练完成！LoRA 权重保存在: {final_path}")
    print(f"   下一步: python training/merge_and_deploy.py --lora {final_path} --base {args.model}")


if __name__ == "__main__":
    main()
