#!/usr/bin/env python
# training/merge_and_deploy.py — 合并 LoRA → 完整模型 + 注册到应用
"""
将 QLoRA 训练产出的适配器合并到基础模型，生成可独立使用的完整模型。

用法:
  # 合并权重
  python training/merge_and_deploy.py \
    --lora ./lora_output/final \
    --base Qwen/Qwen2-7B-Instruct \
    --output ./models/history-translator-7b

  # 合并后直接测试
  python training/merge_and_deploy.py ... --test "The Treaty of Versailles imposed..."
"""

import argparse
import json
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


def merge_model(base_model_id: str, lora_path: str, output_path: str):
    """合并 LoRA 适配器到基础模型"""
    print(f"📦 加载基础模型: {base_model_id}")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)

    print(f"🔗 加载 LoRA 适配器: {lora_path}")
    model = PeftModel.from_pretrained(base_model, lora_path)

    print("🔧 合并权重...")
    merged = model.merge_and_unload()

    print(f"💾 保存合并模型: {output_path}")
    Path(output_path).mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)

    # 保存配置信息
    config = {
        "base_model": base_model_id,
        "lora_source": lora_path,
        "model_type": "history-translator",
        "description": "专业历史著作翻译模型 - QLoRA微调",
    }
    with open(Path(output_path) / "training_config.json", "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"✅ 合并完成: {output_path}")
    return output_path


def test_model(model_path: str, test_text: str):
    """快速测试合并后的模型"""
    print(f"\n🧪 测试模型: {model_path}")
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    system = "你是一位精通历史学术著作翻译的专家。保持术语一致、风格学术化、准确完整。"
    prompt = f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n将以下英文翻译为中文：\n{test_text}<|im_end|>\n<|im_start|>assistant\n"

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.1,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
        )
    response = tokenizer.decode(outputs[0][len(inputs.input_ids[0]) :], skip_special_tokens=True)
    print(f"   原文: {test_text[:100]}...")
    print(f"   译文: {response.strip()}")


def main():
    parser = argparse.ArgumentParser(description="合并 LoRA + 部署")
    parser.add_argument("--lora", required=True, help="LoRA 权重路径")
    parser.add_argument("--base", default="Qwen/Qwen2-7B-Instruct")
    parser.add_argument("--output", default="./models/history-translator-7b")
    parser.add_argument("--test", default=None)
    args = parser.parse_args()

    output = merge_model(args.base, args.lora, args.output)

    # 注册到应用配置
    register_path = Path("backend") / "models" / "custom_models.json"
    register_path.parent.mkdir(parents=True, exist_ok=True)
    models = {}
    if register_path.exists():
        models = json.loads(register_path.read_text())
    models["history-translator"] = {
        "name": "历史著作翻译模型 (微调)",
        "path": str(Path(args.output).resolve()),
        "base_model": args.base,
        "lora_source": args.lora,
    }
    register_path.write_text(json.dumps(models, ensure_ascii=False, indent=2))
    print(f"📋 已注册到: {register_path}")

    if args.test:
        test_model(output, args.test)

    print("\n💡 使用方式:")
    print(f"   在配置面板中选择「本地模型」，输入: {Path(args.output).resolve()}")
    print(f"   或在 config.py 中设置环境变量: LOCAL_TRANSLATE_MODEL={Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
