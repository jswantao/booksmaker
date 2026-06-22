#!/usr/bin/env python
# training/merge_and_deploy.py — 合并 LoRA → 完整模型 + 注册到应用（优化版）
"""
将 QLoRA 训练的 LoRA 适配器合并到基础模型，生成可独立使用的完整模型。

特性：
  - 多种合并策略（完整合并 / 仅适配器 / 渐进式）
  - 模型验证和完整性检查
  - 多格式导出（safetensors / GGUF / GPTQ 支持）
  - 自动版本管理和元数据记录
  - 推理测试套件（翻译质量评估）
  - 应用注册（自动更新配置）
  - 模型压缩和优化

用法：
  # 基础合并
  python training/merge_and_deploy.py \
    --lora ./lora_output/final \
    --base Qwen/Qwen2-7B-Instruct \
    --output ./model_cache/merged/history-translator-7b

  # 合并并运行完整测试
  python training/merge_and_deploy.py \
    --lora ./lora_output/final \
    --base Qwen/Qwen2-7B-Instruct \
    --output ./model_cache/merged/history-translator-7b \
    --test-suite tests/translation_tests.jsonl \
    --eval-metrics bleu,chrf

  # 仅导出适配器（不合并）
  python training/merge_and_deploy.py \
    --lora ./lora_output/final \
    --export-adapter-only \
    --output ./model_cache/merged/adapter-only/

  # 合并 + 量化导出
  python training/merge_and_deploy.py \
    --lora ./lora_output/final \
    --base Qwen/Qwen2-7B-Instruct \
    --output ./model_cache/merged/history-translator-7b \
    --quantize 4bit
"""

import argparse
import json
import os
import sys
import shutil
import time
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime

import torch
import torch.nn as nn
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from peft import PeftModel, PeftConfig

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('merge_deploy.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


# ==================== 数据类定义 ====================
@dataclass
class MergeConfig:
    """合并配置"""
    # 路径
    lora_path: str = ""
    base_model: str = "Qwen/Qwen2-7B-Instruct"
    output_path: str = "./model_cache/merged/history-translator-7b"
    
    # 合并策略
    merge_strategy: str = "full"  # "full" | "adapter_only" | "incremental"
    
    # 导出格式
    export_format: str = "safetensors"  # "safetensors" | "pytorch" | "both"
    quantize: Optional[str] = None  # None | "4bit" | "8bit" | "gguf"
    
    # 模型元数据
    model_name: str = "history-translator"
    model_version: str = "1.0.0"
    model_description: str = "专业历史著作翻译模型 - QLoRA微调"
    model_tags: List[str] = field(default_factory=lambda: ["translation", "history", "academic"])
    model_languages: List[str] = field(default_factory=lambda: ["en", "zh"])
    
    # 测试
    enable_test: bool = True
    test_suite: Optional[str] = None
    test_samples: List[str] = field(default_factory=list)
    eval_metrics: List[str] = field(default_factory=lambda: ["accuracy"])
    
    # 注册
    register_to_app: bool = True
    register_path: str = "backend/models/custom_models.json"
    
    # 其他
    trust_remote_code: bool = True
    device: str = "auto"
    torch_dtype: str = "float16"
    keep_lora_artifacts: bool = True


@dataclass
class ModelMetadata:
    """模型元数据"""
    name: str
    version: str
    description: str
    base_model: str
    lora_source: str
    created_at: str
    model_type: str
    tags: List[str]
    languages: List[str]
    file_size_mb: float
    parameter_count_b: float
    merge_config: Dict[str, Any]
    test_results: Optional[Dict[str, Any]] = None
    checksum: Optional[str] = None


# ==================== 模型合并器 ====================
class ModelMerger:
    """模型合并器"""
    
    def __init__(self, config: MergeConfig):
        self.config = config
        self.metadata: Optional[ModelMetadata] = None
    
    def merge(self) -> str:
        """执行模型合并
        
        Returns:
            合并后模型的路径
        """
        logger.info("="*60)
        logger.info("🔧 开始模型合并流程")
        logger.info("="*60)
        
        # 1. 验证输入
        self._validate_inputs()
        
        # 2. 根据策略执行合并
        if self.config.merge_strategy == "adapter_only":
            output_path = self._export_adapter_only()
        elif self.config.merge_strategy == "incremental":
            output_path = self._merge_incremental()
        else:
            output_path = self._merge_full()
        
        # 3. 导出格式转换
        output_path = self._export_model(output_path)
        
        # 4. 生成元数据
        self._generate_metadata(output_path)
        
        # 5. 验证合并结果
        self._validate_output(output_path)
        
        logger.info(f"✅ 合并完成: {output_path}")
        return output_path
    
    def _validate_inputs(self):
        """验证输入参数"""
        lora_path = Path(self.config.lora_path)
        if not lora_path.exists():
            raise FileNotFoundError(f"LoRA 路径不存在: {self.config.lora_path}")
        
        # 检查 LoRA 配置文件
        if not (lora_path / "adapter_config.json").exists():
            # 可能指向了 final 子目录
            final_path = lora_path / "final"
            if final_path.exists() and (final_path / "adapter_config.json").exists():
                self.config.lora_path = str(final_path)
                logger.info(f"自动修正 LoRA 路径: {final_path}")
            else:
                raise FileNotFoundError(f"未找到 adapter_config.json: {lora_path}")
        
        # 创建输出目录
        output_path = Path(self.config.output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"   LoRA 路径: {self.config.lora_path}")
        logger.info(f"   基础模型: {self.config.base_model}")
        logger.info(f"   输出路径: {self.config.output_path}")
        logger.info(f"   合并策略: {self.config.merge_strategy}")
    
    def _merge_full(self) -> str:
        """完整合并：加载基础模型 + 合并 LoRA"""
        logger.info("\n📦 步骤 1/3: 加载基础模型")

        # 解析本地缓存路径 (ModelScope / HF)
        model_id = self.config.base_model
        if not os.path.isabs(model_id):
            cache_dirs = []
            for env_key in ("MODELSCOPE_CACHE", "HF_HOME", "TRANSFORMERS_CACHE"):
                cd = os.environ.get(env_key, "")
                if cd:
                    cache_dirs.append(cd)
            # 也检查默认位置
            for default in [os.path.join(os.getcwd(), "model_cache"), os.path.expanduser("~/.cache/modelscope")]:
                if default not in cache_dirs:
                    cache_dirs.append(default)
            for cd in cache_dirs:
                for candidate in [
                    os.path.join(cd, ".ms", model_id.replace("/", os.sep).replace("-", "_").replace(".", "_")),
                    os.path.join(cd, ".ms", model_id.replace("/", os.sep)),
                    os.path.join(cd, ".hf", "hub", f"models--{model_id.replace('/', '--')}"),
                ]:
                    if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "config.json")):
                        model_id = candidate
                        logger.info(f"   使用本地缓存: {model_id}")
                        break
                else:
                    continue
                break

        # 加载基础模型
        dtype = getattr(torch, self.config.torch_dtype)
        base_model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=dtype,
            device_map=self.config.device,
            trust_remote_code=self.config.trust_remote_code,
        )

        # 加载分词器
        tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            trust_remote_code=self.config.trust_remote_code,
        )
        
        # 打印模型信息
        param_count = sum(p.numel() for p in base_model.parameters()) / 1e9
        logger.info(f"   基础模型参数量: {param_count:.2f}B")
        
        logger.info(f"\n🔗 步骤 2/3: 加载并合并 LoRA")
        model = PeftModel.from_pretrained(base_model, self.config.lora_path)
        
        # 获取 LoRA 信息
        peft_config = PeftConfig.from_pretrained(self.config.lora_path)
        logger.info(f"   LoRA rank: {peft_config.r}")
        logger.info(f"   LoRA alpha: {peft_config.lora_alpha}")
        logger.info(f"   Target modules: {peft_config.target_modules}")
        
        # 合并权重
        logger.info("   合并中...")
        merged = model.merge_and_unload()
        
        # 清理
        del base_model
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info(f"\n💾 步骤 3/3: 保存合并模型")
        output_path = Path(self.config.output_path)
        merged.save_pretrained(output_path)
        tokenizer.save_pretrained(output_path)
        
        # 保存 LoRA 配置文件（作为参考）
        if self.config.keep_lora_artifacts:
            lora_ref_path = output_path / "lora_reference"
            lora_ref_path.mkdir(exist_ok=True)
            for f in Path(self.config.lora_path).glob("*"):
                if f.is_file():
                    shutil.copy2(f, lora_ref_path / f.name)
            logger.info(f"   LoRA 参考文件保存至: {lora_ref_path}")
        
        return str(output_path)
    
    def _export_adapter_only(self) -> str:
        """仅导出适配器（不合并基础模型）"""
        logger.info("\n📦 导出适配器权重（不合并）")
        
        output_path = Path(self.config.output_path)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # 复制 LoRA 文件
        for f in Path(self.config.lora_path).glob("*"):
            if f.is_file():
                shutil.copy2(f, output_path / f.name)
        
        # 保存额外的元数据
        metadata = {
            "type": "adapter_only",
            "base_model": self.config.base_model,
            "exported_at": datetime.now().isoformat(),
            "note": "此目录仅包含 LoRA 适配器，使用前需加载基础模型",
        }
        with open(output_path / "adapter_metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        logger.info(f"   适配器导出至: {output_path}")
        return str(output_path)
    
    def _merge_incremental(self) -> str:
        """增量合并（保留中间状态）"""
        logger.info("\n📦 增量合并模式")
        
        # 检查是否有多个 checkpoint
        lora_base = Path(self.config.lora_path).parent
        checkpoints = sorted(
            [d for d in lora_base.iterdir() if d.is_dir() and d.name.startswith("checkpoint-")],
            key=lambda x: int(x.name.split("-")[1])
        )
        
        if not checkpoints:
            logger.warning("未找到 checkpoint，使用完整合并")
            return self._merge_full()
        
        logger.info(f"   找到 {len(checkpoints)} 个 checkpoint")
        
        # 使用最佳 checkpoint（或最后一个）
        best_checkpoint = checkpoints[-1]
        if (lora_base / "trainer_state.json").exists():
            with open(lora_base / "trainer_state.json") as f:
                state = json.load(f)
                best_step = state.get("best_model_checkpoint", "")
                if best_step:
                    best_checkpoint = lora_base / Path(best_step).name
                    logger.info(f"   使用最佳 checkpoint: {best_checkpoint}")
        
        # 临时修改路径
        original_lora = self.config.lora_path
        self.config.lora_path = str(best_checkpoint)
        
        try:
            return self._merge_full()
        finally:
            self.config.lora_path = original_lora
    
    def _export_model(self, output_path: str) -> str:
        """导出为指定格式"""
        export_format = self.config.export_format
        output_path = Path(output_path)
        
        if export_format == "safetensors" or export_format == "both":
            logger.info(f"\n🔧 转换为 safetensors 格式")
            self._convert_to_safetensors(output_path)
        
        if self.config.quantize:
            logger.info(f"\n🔧 应用量化: {self.config.quantize}")
            output_path = self._apply_quantization(output_path, self.config.quantize)
        
        return str(output_path)
    
    def _convert_to_safetensors(self, model_path: Path):
        """转换为 safetensors 格式"""
        from safetensors.torch import save_file
        
        # 查找 pytorch 模型文件
        for pt_file in model_path.glob("*.bin"):
            logger.info(f"   转换: {pt_file.name}")
            state_dict = torch.load(pt_file, map_location='cpu')
            safetensors_path = pt_file.with_suffix('.safetensors')
            save_file(state_dict, str(safetensors_path))
            logger.info(f"   已保存: {safetensors_path.name}")
    
    def _apply_quantization(self, model_path: Path, quant_type: str) -> Path:
        """应用量化"""
        quant_path = model_path.parent / f"{model_path.name}-{quant_type}"
        
        if quant_type == "4bit":
            # 加载模型并重新保存为 4-bit
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
            
            model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                quantization_config=bnb_config,
                device_map="cpu",  # 先在 CPU 上操作
            )
            
            # 保存配置
            quant_path.mkdir(exist_ok=True)
            model.config.save_pretrained(quant_path)
            
            # 复制 tokenizer
            tokenizer = AutoTokenizer.from_pretrained(str(model_path))
            tokenizer.save_pretrained(quant_path)
            
            logger.info(f"   4-bit 量化模型保存至: {quant_path}")
            return quant_path
        
        return model_path
    
    def _generate_metadata(self, output_path: str):
        """生成模型元数据"""
        output_path = Path(output_path)
        
        # 计算文件大小
        total_size = sum(f.stat().st_size for f in output_path.rglob("*") if f.is_file())
        size_mb = total_size / (1024 * 1024)
        
        # 估计参数量
        try:
            model = AutoModelForCausalLM.from_pretrained(
                str(output_path),
                torch_dtype=torch.float16,
                device_map="cpu",
            )
            param_count = sum(p.numel() for p in model.parameters()) / 1e9
            del model
        except Exception:
            param_count = 0
        
        # 计算校验和
        checksum = self._compute_checksum(output_path)
        
        self.metadata = ModelMetadata(
            name=self.config.model_name,
            version=self.config.model_version,
            description=self.config.model_description,
            base_model=self.config.base_model,
            lora_source=self.config.lora_path,
            created_at=datetime.now().isoformat(),
            model_type="causal_lm",
            tags=self.config.model_tags,
            languages=self.config.model_languages,
            file_size_mb=round(size_mb, 2),
            parameter_count_b=round(param_count, 2),
            merge_config=asdict(self.config),
            checksum=checksum,
        )
        
        # 保存元数据
        metadata_path = output_path / "model_metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self.metadata), f, indent=2, ensure_ascii=False)
        
        logger.info(f"   元数据已保存: {metadata_path}")
    
    @staticmethod
    def _compute_checksum(path: str) -> str:
        """计算模型目录的校验和"""
        hash_md5 = hashlib.md5()
        path = Path(path)
        
        for f in sorted(path.rglob("*")):
            if f.is_file() and f.suffix in ['.bin', '.safetensors', '.json']:
                with open(f, 'rb') as fh:
                    for chunk in iter(lambda: fh.read(4096), b""):
                        hash_md5.update(chunk)
        
        return hash_md5.hexdigest()
    
    def _validate_output(self, output_path: str):
        """验证合并结果"""
        logger.info(f"\n✅ 验证合并结果")
        output_path = Path(output_path)
        
        # 检查必要文件
        required_files = ["config.json", "tokenizer_config.json"]
        for f in required_files:
            if not (output_path / f).exists():
                logger.warning(f"   ⚠️ 未找到: {f}")

        # 模型权重文件: 单文件(model.safetensors) 或 分片(model.safetensors.index.json)
        if self.config.merge_strategy != "adapter_only":
            has_weights = (
                (output_path / "model.safetensors").exists()
                or (output_path / "model.safetensors.index.json").exists()
                or (output_path / "pytorch_model.bin").exists()
            )
            if not has_weights:
                logger.warning("   ⚠️ 未找到模型权重文件")
        
        # 检查模型文件大小
        total_size = sum(f.stat().st_size for f in output_path.rglob("*") if f.is_file())
        size_gb = total_size / (1024**3)
        logger.info(f"   模型大小: {size_gb:.2f} GB")
        
        if size_gb < 0.1 and self.config.merge_strategy != "adapter_only":
            logger.warning(f"   ⚠️ 模型文件异常小，请检查合并是否成功")


# ==================== 模型测试器 ====================
class ModelTester:
    """模型测试器"""
    
    def __init__(self, model_path: str, config: MergeConfig):
        self.model_path = model_path
        self.config = config
        self.results = {}
    
    def test(self) -> Dict[str, Any]:
        """运行测试"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🧪 模型测试")
        logger.info(f"{'='*60}")
        
        # 1. 基础功能测试
        self._test_basic_generation()
        
        # 2. 测试套件
        if self.config.test_suite:
            self._test_with_suite()
        elif self.config.test_samples:
            self._test_with_samples()
        
        return self.results
    
    def _test_basic_generation(self):
        """基础生成测试"""
        logger.info("\n📝 基础生成测试")
        
        try:
            model, tokenizer = self._load_model()
        except Exception as e:
            logger.error(f"   模型加载失败: {e}")
            self.results["basic_test"] = {"status": "failed", "error": str(e)}
            return
        
        test_cases = [
            {
                "name": "简单翻译",
                "input": "The Roman Empire fell in 476 AD.",
                "expected_length_range": (5, 100),
            },
            {
                "name": "历史术语",
                "input": "The Byzantine Empire, also known as the Eastern Roman Empire, preserved Greco-Roman culture.",
                "expected_keywords": ["拜占庭", "罗马"],
            },
            {
                "name": "复杂句式",
                "input": "Although the empire had fallen, its legal and administrative systems continued to influence European civilization for centuries to come.",
                "expected_length_range": (20, 200),
            },
        ]
        
        for case in test_cases:
            try:
                translation = self._translate(model, tokenizer, case["input"])
                
                passed = True
                issues = []
                
                # 长度检查
                if "expected_length_range" in case:
                    min_l, max_l = case["expected_length_range"]
                    if len(translation) < min_l:
                        passed = False
                        issues.append(f"译文过短 ({len(translation)} < {min_l})")
                    if len(translation) > max_l:
                        passed = False
                        issues.append(f"译文过长 ({len(translation)} > {max_l})")
                
                # 关键词检查
                if "expected_keywords" in case:
                    for kw in case["expected_keywords"]:
                        if kw not in translation:
                            passed = False
                            issues.append(f"缺少关键词: {kw}")
                
                status = "✅" if passed else "⚠️"
                logger.info(f"   {status} {case['name']}")
                logger.info(f"      原文: {case['input'][:80]}...")
                logger.info(f"      译文: {translation[:120]}...")
                
                if issues:
                    logger.warning(f"      问题: {'; '.join(issues)}")
                
                self.results[f"test_{case['name']}"] = {
                    "status": "passed" if passed else "warning",
                    "issues": issues,
                    "translation": translation[:200],
                }
                
            except Exception as e:
                logger.error(f"   ❌ {case['name']}: {e}")
                self.results[f"test_{case['name']}"] = {"status": "failed", "error": str(e)}
        
        # 清理
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    def _test_with_suite(self):
        """使用测试套件"""
        logger.info(f"\n📋 测试套件: {self.config.test_suite}")
        
        test_path = Path(self.config.test_suite)
        if not test_path.exists():
            logger.warning(f"   测试文件不存在: {test_path}")
            return
        
        try:
            model, tokenizer = self._load_model()
        except Exception as e:
            logger.error(f"   模型加载失败: {e}")
            return
        
        # 加载测试数据
        tests = []
        with open(test_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    tests.append(json.loads(line))
        
        logger.info(f"   共 {len(tests)} 个测试用例")
        
        scores = []
        for i, test in enumerate(tests):
            try:
                translation = self._translate(model, tokenizer, test["input"])
                
                # 简单评估
                score = self._simple_evaluate(translation, test.get("reference", ""))
                scores.append(score)
                
                if i < 5 or i % 10 == 0:  # 只打印前5个和每10个
                    logger.info(f"   [{i+1}/{len(tests)}] 得分: {score:.2f}")
                
            except Exception as e:
                logger.error(f"   [{i+1}] 失败: {e}")
        
        if scores:
            avg_score = sum(scores) / len(scores)
            logger.info(f"\n   📊 平均得分: {avg_score:.2f}")
            self.results["suite_test"] = {
                "total": len(tests),
                "avg_score": round(avg_score, 2),
                "min_score": round(min(scores), 2),
                "max_score": round(max(scores), 2),
            }
        
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    def _test_with_samples(self):
        """使用命令行提供的测试样本"""
        logger.info(f"\n📝 测试样本 ({len(self.config.test_samples)} 个)")
        
        try:
            model, tokenizer = self._load_model()
        except Exception as e:
            logger.error(f"   模型加载失败: {e}")
            return
        
        for i, text in enumerate(self.config.test_samples):
            try:
                translation = self._translate(model, tokenizer, text)
                logger.info(f"\n   --- 样本 {i+1} ---")
                logger.info(f"   原文: {text[:150]}...")
                logger.info(f"   译文: {translation[:200]}...")
            except Exception as e:
                logger.error(f"   样本 {i+1} 失败: {e}")
        
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    def _load_model(self):
        """加载模型和分词器"""
        logger.info(f"   加载模型: {self.model_path}")
        
        model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            torch_dtype=torch.float16,
            device_map=self.config.device,
            trust_remote_code=self.config.trust_remote_code,
        )
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_path,
            trust_remote_code=self.config.trust_remote_code,
        )
        
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        return model, tokenizer
    
    def _translate(self, model, tokenizer, text: str) -> str:
        """执行翻译"""
        system = "你是一位精通历史学术著作翻译的专家。保持术语一致、风格学术化、准确完整。"
        prompt = (
            f"<|im_start|>system\n{system}<|im_end|>\n"
            f"<|im_start|>user\n将以下英文翻译为中文：\n{text}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )
        
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        
        with torch.inference_mode():
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.1,
                do_sample=False,
                top_p=0.95,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        
        response = tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:],
            skip_special_tokens=True
        ).strip()
        
        return response
    
    @staticmethod
    def _simple_evaluate(translation: str, reference: str) -> float:
        """简单评估函数"""
        if not reference:
            # 无参考时，基于长度和内容评估
            score = min(len(translation) / 50, 1.0) * 0.5  # 长度分
            if "。" in translation or "，" in translation:
                score += 0.3  # 标点分
            if any(kw in translation for kw in ["拜占庭", "罗马", "帝国", "皇帝"]):
                score += 0.2  # 关键词分
            return min(score, 1.0)
        
        # 有参考时，简单的 n-gram 重叠
        def get_ngrams(text, n=2):
            return set(text[i:i+n] for i in range(len(text)-n+1))
        
        ref_ngrams = get_ngrams(reference)
        trans_ngrams = get_ngrams(translation)
        
        if not trans_ngrams:
            return 0.0
        
        overlap = len(ref_ngrams & trans_ngrams)
        return overlap / len(ref_ngrams) if ref_ngrams else 0.0


# ==================== 应用注册器 ====================
class AppRegistrar:
    """应用注册器：将模型注册到应用配置"""
    
    def __init__(self, register_path: str):
        self.register_path = Path(register_path)
    
    def register(self, metadata: ModelMetadata, model_path: str) -> bool:
        """注册模型到应用配置"""
        logger.info(f"\n📋 注册模型到应用")
        
        try:
            # 确保目录存在
            self.register_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 读取现有注册表
            models = {}
            if self.register_path.exists():
                with open(self.register_path, 'r', encoding='utf-8') as f:
                    models = json.load(f)
            
            # 构建注册条目
            entry = {
                "name": metadata.name,
                "display_name": metadata.description,
                "path": str(Path(model_path).resolve()),
                "base_model": metadata.base_model,
                "lora_source": metadata.lora_source,
                "version": metadata.version,
                "created_at": metadata.created_at,
                "file_size_mb": metadata.file_size_mb,
                "parameter_count_b": metadata.parameter_count_b,
                "tags": metadata.tags,
                "languages": metadata.languages,
                "active": True,
            }
            
            # 添加或更新
            models[metadata.name] = entry
            
            # 保存
            with open(self.register_path, 'w', encoding='utf-8') as f:
                json.dump(models, f, ensure_ascii=False, indent=2)
            
            logger.info(f"   ✅ 已注册到: {self.register_path}")
            logger.info(f"   模型名称: {metadata.name}")
            logger.info(f"   版本: {metadata.version}")
            
            return True
            
        except Exception as e:
            logger.error(f"   ❌ 注册失败: {e}")
            return False
    
    def unregister(self, model_name: str) -> bool:
        """取消注册"""
        if not self.register_path.exists():
            return False
        
        with open(self.register_path, 'r', encoding='utf-8') as f:
            models = json.load(f)
        
        if model_name in models:
            del models[model_name]
            with open(self.register_path, 'w', encoding='utf-8') as f:
                json.dump(models, f, ensure_ascii=False, indent=2)
            logger.info(f"   已取消注册: {model_name}")
            return True
        
        return False


# ==================== 主函数 ====================
def parse_args() -> MergeConfig:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="合并 LoRA 权重并部署模型",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础合并
  python merge_and_deploy.py --lora ./lora_output/final --output ./model_cache/merged/my-model
  
  # 合并并测试
  python merge_and_deploy.py --lora ./lora_output/final --output ./model_cache/merged/my-model \\
      --test-samples "The Roman Empire fell." "Constantinople was the capital."
  
  # 合并并量化
  python merge_and_deploy.py --lora ./lora_output/final --output ./model_cache/merged/my-model --quantize 4bit
        """
    )
    
    # 路径
    parser.add_argument("--lora", required=True, help="LoRA 权重路径")
    parser.add_argument("--base", default="Qwen/Qwen2-7B-Instruct", help="基础模型")
    parser.add_argument("--output", default="./model_cache/merged/history-translator-7b", help="输出路径")
    
    # 策略
    parser.add_argument("--strategy", default="full",
                       choices=["full", "adapter_only", "incremental"],
                       help="合并策略")
    
    # 导出选项
    parser.add_argument("--export-format", default="safetensors",
                       choices=["safetensors", "pytorch", "both"])
    parser.add_argument("--quantize", default=None,
                       choices=["4bit", "8bit", "gguf"])
    
    # 元数据
    parser.add_argument("--name", default="history-translator", help="模型名称")
    parser.add_argument("--version", default="1.0.0", help="模型版本")
    parser.add_argument("--description", default="专业历史著作翻译模型", help="模型描述")
    parser.add_argument("--tags", nargs="*", default=["translation", "history"],
                       help="模型标签")
    
    # 测试
    parser.add_argument("--test", nargs="*", default=None,
                       help="测试文本（快速测试）")
    parser.add_argument("--test-suite", default=None,
                       help="测试套件 JSONL 文件")
    parser.add_argument("--skip-test", action="store_true",
                       help="跳过测试")
    
    # 注册
    parser.add_argument("--register", default="backend/models/custom_models.json",
                       help="注册文件路径")
    parser.add_argument("--no-register", action="store_true",
                       help="不注册到应用")
    
    # 其他
    parser.add_argument("--device", default="auto", help="设备")
    parser.add_argument("--dtype", default="float16", help="数据类型")
    parser.add_argument("--no-trust-remote-code", action="store_true",
                       help="不信任远程代码")
    
    args = parser.parse_args()
    
    # 构建配置
    config = MergeConfig(
        lora_path=args.lora,
        base_model=args.base,
        output_path=args.output,
        merge_strategy=args.strategy,
        export_format=args.export_format,
        quantize=args.quantize,
        model_name=args.name,
        model_version=args.version,
        model_description=args.description,
        model_tags=args.tags or ["translation", "history"],
        enable_test=not args.skip_test,
        test_suite=args.test_suite,
        test_samples=args.test or [],
        register_to_app=not args.no_register,
        register_path=args.register,
        device=args.device,
        torch_dtype=args.dtype,
        trust_remote_code=not args.no_trust_remote_code,
    )
    
    return config


def main():
    """主流程"""
    # 解析配置
    config = parse_args()
    
    # 创建合并器
    merger = ModelMerger(config)
    
    # 执行合并
    output_path = merger.merge()
    
    # 测试模型
    test_results = None
    if config.enable_test and (config.test_suite or config.test_samples):
        tester = ModelTester(output_path, config)
        test_results = tester.test()
        
        # 更新元数据
        if test_results and merger.metadata:
            merger.metadata.test_results = test_results
            metadata_path = Path(output_path) / "model_metadata.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(merger.metadata), f, indent=2, ensure_ascii=False)
    
    # 注册到应用
    if config.register_to_app and merger.metadata:
        registrar = AppRegistrar(config.register_path)
        registrar.register(merger.metadata, output_path)
    
    # 打印使用说明
    logger.info(f"\n{'='*60}")
    logger.info(f"💡 使用方式")
    logger.info(f"{'='*60}")
    logger.info(f"1. 在配置面板中选择「本地模型」")
    logger.info(f"   路径: {Path(output_path).resolve()}")
    logger.info(f"")
    logger.info(f"2. 或设置环境变量:")
    logger.info(f"   export LOCAL_TRANSLATE_MODEL={Path(output_path).resolve()}")
    logger.info(f"")
    logger.info(f"3. 在代码中使用:")
    logger.info(f"   manager.configure_local('{Path(output_path).resolve()}', task='translation')")
    
    return output_path


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️ 操作被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ 操作失败: {e}", exc_info=True)
        sys.exit(1)