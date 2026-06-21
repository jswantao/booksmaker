# 历史著作翻译模型微调指南

## 概览

基于 QLoRA (4-bit Quantized Low-Rank Adaptation) 在消费级 GPU 上微调翻译模型。

### 硬件要求
- **7B 模型**: 8GB+ 显存 (RTX 3070/4060 及以上)
- **1.5B 模型**: 4GB+ 显存 (GTX 1060 及以上)
- 训练时间: 1000 条数据约 20-40 分钟 (7B) / 5-10 分钟 (1.5B)

### 工作流程

```
翻译记忆库 (TM)  ──┐
知识库 (KB)     ──┼──→ export_data.py ──→ train.jsonl
记忆库 (术语)    ──┘                          │
                                         finetune.py (QLoRA)
                                              │
                                         lora_output/final/
                                              │
                                   merge_and_deploy.py
                                              │
                                   models/history-translator-7b/
```

## 快速开始

### 1. 安装训练依赖
```bash
pip install -r training/requirements.txt
```

### 2. 准备训练数据
从项目中已有的翻译记忆库和术语表导出:
```bash
python training/export_data.py \
  --tm-db data/translation_memory.db \
  --memory-dir memory_banks \
  --output data/train.jsonl
```

数据越丰富效果越好。建议至少 500 条样本开始，理想情况 2000+ 条。

### 3. 开始微调
```bash
# 基于 Qwen2-7B (推荐)
python training/finetune.py \
  --model Qwen/Qwen2-7B-Instruct \
  --data data/train.jsonl \
  --output ./lora_output \
  --epochs 3 \
  --batch_size 1 \
  --gradient_accumulation 8

# 基于混元 MT-7B (翻译专用基础)
python training/finetune.py \
  --model Tencent-Hunyuan/Hunyuan-MT-7B \
  --data data/train.jsonl \
  --output ./lora_output \
  --epochs 2
```

### 4. 合并权重 + 测试
```bash
python training/merge_and_deploy.py \
  --lora ./lora_output/final \
  --base Qwen/Qwen2-7B-Instruct \
  --output ./models/history-translator-7b \
  --test "The Treaty of Westphalia marked the beginning of the modern state system."
```

### 5. 在应用中使用
在配置面板中:
- LLM 提供者: **本地模型**
- 本地翻译模型: `./models/history-translator-7b` (填合并后的路径)
- 保存并测试

模型加载时会自动检测并合并同目录下的 LoRA 适配器。

## 数据策略

### 数据分层 (按优先级)
| 优先级 | 来源 | 说明 |
|--------|------|------|
| ⭐⭐⭐ | 翻译记忆库 | 精校过的翻译对，质量最高 |
| ⭐⭐ | 术语表 | 确保专有名词一致性 |
| ⭐ | 知识库 | 提供领域上下文 |

### 手工扩充数据
在 `data/train.jsonl` 中手工添加高质量翻译对:
```json
{"instruction": "翻译以下历史著作段落...", "input": "原文", "output": "精校译文"}
```

## 参数调优

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--epochs` | 3 | 数据少(500-)→5, 数据多(2000+)→2 |
| `--lora_r` | 16 | 数据多可增至32 |
| `--learning_rate` | 2e-4 | 训练不稳定时降至1e-4 |
| `--gradient_accumulation` | 8 | 显存不足时增大(dummy batch=1×16) |
| `--max_length` | 1024 | 段落较长可增至2048 |

## 常见问题

**Q: 训练中断了怎么办？**
A: 用 `--resume_from lora_output/checkpoint-400` 从 checkpoint 恢复。

**Q: 模型效果不好？**
A: 增加数据量(目标2000+条)、提高数据质量(人工校对翻译记忆)、增加 epochs。

**Q: OOM 显存不足？**
A: 增大 `--gradient_accumulation`、换用 1.5B 模型 (`Qwen/Qwen2.5-1.5B-Instruct`)。
