"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ShinyButton } from "@/components/ui/shiny-button";
import {
  useTrainingData,
  useExportTrainingData,
  useStartTraining,
  useStopTraining,
  useTrainingStatus,
  useTrainingLogs,
  useTrainedModels,
  useTrainingEnvCheck,
  useAvailableBaseModels,
  useUpdateConfig,
} from "@/hooks/use-training";
import { loadSeedData as apiLoadSeed, importParagraphPairs } from "@/lib/api";
import { toast } from "sonner";
import {
  Database, Zap, Square, Brain, Cpu, RefreshCw,
  Download, Sparkles, Plus, X, Upload, HardDrive,
  Activity, Gauge,
} from "lucide-react";

import { PhaseStepper } from "./phase-stepper";
import { LossChart } from "./loss-chart";
import { LogViewer } from "./log-viewer";
import { TrainingSummaryDialog } from "./training-summary-dialog";
import { MergeDialog } from "./merge-dialog";
import { TrainingHistoryCard } from "./training-history-card";
import type { TrainingPhase } from "@/types/api";

export function TrainingTab() {
  // ---- Data layer ----
  const { data: dataStatus, refetch: refetchData } = useTrainingData();
  const exportData = useExportTrainingData();
  const [dataOutput] = useState("data/train.jsonl");
  const { data: availableModels } = useAvailableBaseModels();
  const updateConfigMutation = useUpdateConfig();

  // ---- Training config ----
  const [baseModel, setBaseModel] = useState("Tencent-Hunyuan/Hy-MT2-1.8B");
  const [epochs, setEpochs] = useState(3);
  const [batchSize, setBatchSize] = useState(1);
  const [gradAccum, setGradAccum] = useState(8);
  const [learningRate, setLearningRate] = useState(2e-4);
  const [loraR, setLoraR] = useState(16);
  const [loraAlpha, setLoraAlpha] = useState(32);
  const [incremental, setIncremental] = useState(false);
  const [resumeLora, setResumeLora] = useState("");
  const [customModelPath, setCustomModelPath] = useState("");

  // ---- Training state ----
  const startTraining = useStartTraining();
  const stopTraining = useStopTraining();
  const [isRunning, setIsRunning] = useState(false);
  const polling = isRunning || startTraining.isPending;
  const { data: trainStatus } = useTrainingStatus(polling);
  const [logSince, setLogSince] = useState(0);
  const { data: logData } = useTrainingLogs(polling, logSince);
  const { data: modelsData, refetch: refetchModels } = useTrainedModels();
  const { data: envCheck } = useTrainingEnvCheck();

  // ---- Accumulated log lines ----
  const [allLogLines, setAllLogLines] = useState<string[]>([]);
  useEffect(() => {
    if (logData?.lines?.length) {
      setAllLogLines((prev) => [...prev, ...logData.lines]);
      setLogSince(logData.total);
    }
  }, [logData]);

  // ---- Dialogs ----
  const [showSummary, setShowSummary] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeDefaultPath, setMergeDefaultPath] = useState("");
  const hasShownSummary = useRef(false);

  // ---- Completion detection ----
  useEffect(() => {
    if (trainStatus?.running) {
      setIsRunning(true);
      hasShownSummary.current = false;
    } else if (trainStatus && !trainStatus.running && isRunning) {
      setIsRunning(false);
      if (!hasShownSummary.current) {
        hasShownSummary.current = true;
        setShowSummary(true);
      }
      if (trainStatus.error) {
        toast.error(trainStatus.error);
      } else if (trainStatus.progress >= 99) {
        toast.success("训练完成！");
        refetchModels();
      }
    }
  }, [trainStatus, isRunning, refetchModels]);

  // Reset logs when starting new training
  useEffect(() => {
    if (startTraining.isPending) {
      setAllLogLines([]);
      setLogSince(0);
    }
  }, [startTraining.isPending]);

  // ---- ETA ----
  const eta = useMemo(() => {
    if (!trainStatus?.training_speed || !trainStatus?.total_steps || !trainStatus?.step) return null;
    if (trainStatus.training_speed <= 0) return null;
    const remaining = trainStatus.total_steps - trainStatus.step;
    if (remaining <= 0) return null;
    const seconds = remaining / trainStatus.training_speed;
    if (seconds > 3600) {
      const h = Math.floor(seconds / 3600);
      const m = Math.floor((seconds % 3600) / 60);
      return `${h}h${m}m`;
    }
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m${s}s`;
  }, [trainStatus?.training_speed, trainStatus?.step, trainStatus?.total_steps]);

  // ---- Data handlers ----
  const [queue, setQueue] = useState<Array<{ source: string; target: string }>>([]);
  const [srcInput, setSrcInput] = useState("");
  const [tgtInput, setTgtInput] = useState("");
  const [importingSeed, setImportingSeed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [showBatch, setShowBatch] = useState(false);
  const [batchText, setBatchText] = useState("");

  const cleanHtml = (text: string) => text.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();

  const addToQueue = () => {
    const s = cleanHtml(srcInput).trim();
    const t = cleanHtml(tgtInput).trim();
    if (s.length < 10) { toast.error("原文太短（至少10字符）"); return; }
    if (t.length < 5) { toast.error("译文太短（至少5字符）"); return; }
    if (queue.find((q) => q.source === s)) { toast.error("此翻译对已在队列中"); return; }
    setQueue([...queue, { source: s, target: t }]);
    setSrcInput(""); setTgtInput("");
    toast.success(`已添加 #${queue.length + 1}`);
  };

  const removeFromQueue = (idx: number) => setQueue(queue.filter((_, i) => i !== idx));

  const submitQueue = async () => {
    if (queue.length === 0) { toast.error("队列为空，请先添加翻译对"); return; }
    setSubmitting(true);
    try {
      const r = await importParagraphPairs({ pairs: queue });
      if (r.success) { toast.success(`已导入 ${r.imported} 段`); setQueue([]); refetchData(); }
      else toast.error(r.error || "导入失败");
    } catch { toast.error("提交失败"); }
    finally { setSubmitting(false); }
  };

  const handleLoadSeed = async () => {
    setImportingSeed(true);
    try {
      const r = await apiLoadSeed();
      if (r.success) toast.success(`种子数据已导入: ${r.imported} 条${r.skipped ? ` (跳过${r.skipped}条重复)` : ""}`);
      else toast.error(r.error);
      refetchData();
    } catch { toast.error("导入失败"); }
    finally { setImportingSeed(false); }
  };

  const handleBatchPaste = () => {
    const text = batchText.trim();
    if (!text) return;
    let added = 0;
    try {
      const parsed = JSON.parse(text);
      const pairs = Array.isArray(parsed) ? parsed : [parsed];
      for (const p of pairs) {
        const s = cleanHtml(p.source || p["原文"] || p.input || "");
        const t = cleanHtml(p.target || p["译文"] || p.output || "");
        if (s.length >= 10 && t.length >= 5 && !queue.find((q) => q.source === s)) {
          setQueue((prev) => [...prev, { source: s, target: t }]);
          added++;
        }
      }
    } catch {
      const blocks = text.split(/\n\s*\n/);
      for (const block of blocks) {
        const lines = block.split("\n").filter((l) => l.trim());
        if (lines.length >= 2) {
          const s = cleanHtml(lines[0]);
          const t = cleanHtml(lines[1]);
          if (s.length >= 10 && t.length >= 5 && !queue.find((q) => q.source === s)) {
            setQueue((prev) => [...prev, { source: s, target: t }]);
            added++;
          }
        }
      }
    }
    if (added > 0) { toast.success(`批量添加 ${added} 对`); setBatchText(""); }
    else { toast.error("未识别到有效翻译对"); }
  };

  const handleExport = async () => {
    try {
      const r = await exportData.mutateAsync({ output: dataOutput });
      if (r.success) { toast.success(r.message); refetchData(); }
      else toast.error(r.error);
    } catch { toast.error("导出失败"); }
  };

  const handleStart = async () => {
    setAllLogLines([]);
    setLogSince(0);
    try {
      const modelToUse = customModelPath.trim() || baseModel;
      const r = await startTraining.mutateAsync({
        base_model: modelToUse, data_path: dataOutput, output_dir: "./lora_output",
        epochs, batch_size: batchSize, gradient_accumulation: gradAccum,
        learning_rate: learningRate, lora_r: loraR, lora_alpha: loraAlpha, use_4bit: true,
        resume_from_lora: incremental ? (resumeLora || undefined) : undefined,
      });
      if (r.success) { setIsRunning(true); toast.success("训练已启动"); }
      else toast.error(r.error);
    } catch { toast.error("启动失败"); }
  };

  const handleStop = async () => {
    try { await stopTraining.mutateAsync(); setIsRunning(false); toast.success("已发送停止信号"); }
    catch { toast.error("停止失败"); }
  };

  const handleUseModel = (path: string) => {
    updateConfigMutation.mutate(
      { llm_provider: "local", local_translate_model: path },
      {
        onSuccess: () => toast.success("已将模型配置为翻译模型"),
        onError: () => toast.error("配置失败，请重试"),
      }
    );
  };

  const openMergeDialog = (loraPath?: string) => {
    setMergeDefaultPath(loraPath || "");
    setMergeOpen(true);
  };

  const progress = isRunning ? (trainStatus?.progress || 0) : 0;
  const phase = trainStatus?.phase;
  const loss = trainStatus?.loss;
  const error = trainStatus?.error;

  return (
    <div className="space-y-6">
      {/* ======== 数据准备 ======== */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-lg font-heading flex items-center gap-2">
            <Database className="h-5 w-5" />数据准备
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
            <div className="p-3 rounded-lg border">
              <p className="text-muted-foreground text-xs">翻译记忆</p>
              <b className="text-lg">{dataStatus?.tm_entries ?? "?"}</b>
              <span className="text-xs ml-1">条</span>
            </div>
            <div className="p-3 rounded-lg border">
              <p className="text-muted-foreground text-xs">共享术语</p>
              <b className="text-lg">{dataStatus?.shared_terms ?? "?"}</b>
              <span className="text-xs ml-1">条</span>
            </div>
            <div className="p-3 rounded-lg border">
              <p className="text-muted-foreground text-xs">训练样本</p>
              <b className="text-lg">{dataStatus?.train_samples ?? "?"}</b>
              <span className="text-xs ml-1">条</span>
            </div>
            <div className="p-3 rounded-lg border flex items-center justify-center">
              <Badge variant={dataStatus?.ready ? "default" : "secondary"}>
                {dataStatus?.ready ? "可训练" : "数据不足"}
              </Badge>
            </div>
          </div>

          <div className="flex gap-2 mb-3 flex-wrap">
            <Input value={dataOutput} readOnly placeholder="data/train.jsonl" className="h-8 text-sm flex-1" />
            <Button size="sm" variant="outline" onClick={handleLoadSeed} disabled={importingSeed}>
              <Sparkles className="h-3 w-3 mr-1" />{importingSeed ? "导入中..." : "加载种子数据"}
            </Button>
            <Button size="sm" onClick={handleExport} disabled={exportData.isPending}>
              <Download className="h-3 w-3 mr-1" />{exportData.isPending ? "导出中..." : "导出 TM 数据"}
            </Button>
          </div>

          {/* 翻译对录入 */}
          <div className="mt-4 pt-3 border-t">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium">录入翻译对</span>
              <Badge variant="secondary" className="text-xs">{queue.length} 条待提交</Badge>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">原文 (English)</label>
                <Textarea
                  className="mt-1 min-h-[80px] text-sm resize-y font-sans"
                  placeholder="粘贴英文原文... HTML 标签会自动清理"
                  value={srcInput}
                  onChange={(e) => setSrcInput(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">译文 (中文)</label>
                <Textarea
                  className="mt-1 min-h-[80px] text-sm resize-y font-sans"
                  placeholder="粘贴中文译文..."
                  value={tgtInput}
                  onChange={(e) => setTgtInput(e.target.value)}
                />
              </div>
            </div>
            <div className="flex gap-2 mt-2">
              <Button size="sm" onClick={addToQueue}><Plus className="h-3 w-3 mr-1" />添加到队列</Button>
              <Button size="sm" variant="outline" onClick={submitQueue} disabled={queue.length === 0 || submitting}>
                <Upload className="h-3 w-3 mr-1" />{submitting ? "提交中..." : `提交 ${queue.length} 条`}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowBatch(!showBatch)}>批量粘贴</Button>
            </div>
            {showBatch && (
              <div className="mt-2">
                <Textarea
                  className="min-h-[80px] text-xs font-mono resize-y"
                  placeholder={'支持 JSON: [{"source":"...","target":"..."}]\n或纯文本: 原文\\n译文\\n\\n原文\\n译文'}
                  value={batchText}
                  onChange={(e) => setBatchText(e.target.value)}
                />
                <Button size="sm" variant="ghost" onClick={handleBatchPaste} className="mt-1">识别并导入</Button>
              </div>
            )}
            {queue.length > 0 && (
              <div className="mt-2 border rounded max-h-[120px] overflow-y-auto">
                <div className="p-2 space-y-1">
                  {queue.map((q, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs p-1.5 rounded hover:bg-muted/50 group">
                      <span className="text-muted-foreground shrink-0">{i + 1}.</span>
                      <div className="flex-1 min-w-0">
                        <p className="truncate font-medium">{q.source.substring(0, 80)}</p>
                        <p className="truncate text-green-700 dark:text-green-400">{q.target.substring(0, 80)}</p>
                      </div>
                      <Button
                        variant="ghost" size="sm"
                        className="h-5 w-5 p-0 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 shrink-0"
                        onClick={() => removeFromQueue(i)}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ======== 训练参数 + 监控 ======== */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* ---- 训练参数 ---- */}
        <Card className="xl:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-heading flex items-center gap-2">
              <Brain className="h-4 w-4" />训练参数
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* 环境状态 */}
            {envCheck && (
              <div className="grid grid-cols-4 gap-1 mb-2">
                {Object.entries(envCheck.deps).slice(0, 4).map(([name, status]) => (
                  <Badge
                    key={name}
                    variant={status === "ok" ? "default" : "destructive"}
                    className="text-[10px] justify-center"
                  >
                    {status === "ok" ? "✓" : "✗"} {name.replace(" (LoRA)", "").replace(" (4-bit)", "").replace(" (SFTTrainer)", "")}
                  </Badge>
                ))}
              </div>
            )}
            {envCheck && !envCheck.all_ok && (
              <p className="text-xs text-destructive">依赖缺失！运行: pip install -r training/requirements.txt</p>
            )}
            {envCheck?.gpu_available && (
              <p className="text-xs text-green-600 flex items-center gap-1">
                <Cpu className="h-3 w-3" /> {envCheck.gpu_info}
              </p>
            )}

            <div>
              <label className="text-xs font-medium">基础模型</label>
              <Select value={baseModel} onValueChange={(v) => setBaseModel(v || "Tencent-Hunyuan/Hy-MT2-1.8B")}>
                <SelectTrigger className="mt-1 h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectLabel>推荐模型</SelectLabel>
                    {(availableModels?.recommended ?? []).map((m) => (
                      <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                    ))}
                  </SelectGroup>
                  {(availableModels?.cached?.length ?? 0) > 0 && (
                    <SelectGroup>
                      <SelectLabel>本地缓存</SelectLabel>
                      {availableModels!.cached.map((m) => (
                        <SelectItem key={m.id} value={m.path}>{m.id} ({m.source})</SelectItem>
                      ))}
                    </SelectGroup>
                  )}
                  {(availableModels?.merged?.length ?? 0) > 0 && (
                    <SelectGroup>
                      <SelectLabel>已合并模型</SelectLabel>
                      {availableModels!.merged.map((m) => (
                        <SelectItem key={m.id} value={m.path}>{m.name}{m.base_model ? ` (基于 ${m.base_model})` : ""}</SelectItem>
                      ))}
                    </SelectGroup>
                  )}
                  {(availableModels?.lora_adapters?.length ?? 0) > 0 && (
                    <SelectGroup>
                      <SelectLabel>LoRA 适配器</SelectLabel>
                      {availableModels!.lora_adapters.map((m) => (
                        <SelectItem key={m.id} value={m.path}>{m.name}</SelectItem>
                      ))}
                    </SelectGroup>
                  )}
                </SelectContent>
              </Select>
              <Input
                placeholder="或输入自定义模型路径 / HuggingFace ID..."
                value={customModelPath}
                onChange={(e) => setCustomModelPath(e.target.value)}
                className="mt-1 h-8 text-sm"
              />
            </div>

            {/* 增量训练 */}
            <div className="flex items-center gap-2">
              <Checkbox id="incremental" checked={incremental} onCheckedChange={(v) => setIncremental(!!v)} />
              <label htmlFor="incremental" className="text-xs cursor-pointer">增量训练（基于已有模型）</label>
            </div>
            {incremental && (
              <Select value={resumeLora} onValueChange={(v) => setResumeLora(v || "")}>
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue placeholder="选择已有 LoRA 适配器..." />
                </SelectTrigger>
                <SelectContent>
                  {(modelsData?.models || []).filter((m) => m.type === "lora" || m.name?.startsWith("lora_")).map((m) => (
                    <SelectItem key={m.path} value={m.path}>{m.name}</SelectItem>
                  ))}
                  {(modelsData?.models || []).filter((m) => m.type === "lora" || m.name?.startsWith("lora_")).length === 0 && (
                    <div className="px-2 py-1 text-xs text-muted-foreground">暂无可用的 LoRA 模型</div>
                  )}
                </SelectContent>
              </Select>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div>
                <label className="text-xs font-medium">Epochs</label>
                <Input type="number" value={epochs} onChange={(e) => setEpochs(+e.target.value)} min={1} max={10} className="mt-1 h-8 text-sm" />
              </div>
              <div>
                <label className="text-xs font-medium">Batch Size</label>
                <Input type="number" value={batchSize} onChange={(e) => setBatchSize(+e.target.value)} min={1} max={8} className="mt-1 h-8 text-sm" />
              </div>
              <div>
                <label className="text-xs font-medium">Grad Accum</label>
                <Input type="number" value={gradAccum} onChange={(e) => setGradAccum(+e.target.value)} min={1} max={32} className="mt-1 h-8 text-sm" />
              </div>
              <div>
                <label className="text-xs font-medium">LR</label>
                <Input type="number" value={learningRate} onChange={(e) => setLearningRate(+e.target.value)} step={0.0001} min={1e-5} max={1e-3} className="mt-1 h-8 text-sm font-mono" />
              </div>
              <div>
                <label className="text-xs font-medium">LoRA r</label>
                <Input type="number" value={loraR} onChange={(e) => setLoraR(+e.target.value)} min={4} max={64} className="mt-1 h-8 text-sm" />
              </div>
              <div>
                <label className="text-xs font-medium">LoRA α</label>
                <Input type="number" value={loraAlpha} onChange={(e) => setLoraAlpha(+e.target.value)} min={8} max={128} className="mt-1 h-8 text-sm" />
              </div>
            </div>

            <div className="flex gap-2 pt-1 flex-wrap">
              {!isRunning ? (
                <ShinyButton onClick={handleStart} className="flex-1">
                  <Zap className="h-3 w-3 mr-1" />{startTraining.isPending ? "启动中..." : "开始训练"}
                </ShinyButton>
              ) : (
                <Button variant="destructive" onClick={handleStop} className="flex-1">
                  <Square className="h-3 w-3 mr-1" />停止训练
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* ---- 训练监控 ---- */}
        <Card className="xl:col-span-2">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-base font-heading flex items-center gap-2">
              <Activity className="h-4 w-4" />训练监控
            </CardTitle>
            <div className="flex gap-2 items-center">
              {isRunning && <Badge variant="default" className="animate-pulse">运行中</Badge>}
              {!isRunning && !error && phase !== "complete" && <Badge variant="secondary">空闲</Badge>}
              {phase === "complete" && <Badge variant="default" className="bg-green-600">已完成</Badge>}
              {error && <Badge variant="destructive">异常</Badge>}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* 阶段流水线 */}
            <PhaseStepper currentPhase={phase} />

            {/* 进度条 + ETA */}
            <div>
              <div className="flex justify-between text-xs text-muted-foreground mb-1">
                <span>Epoch {trainStatus?.current_epoch || 0}/{trainStatus?.total_epochs || 0}</span>
                <span>{trainStatus?.step || 0}/{trainStatus?.total_steps || 0} steps</span>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{progress.toFixed(0)}%</span>
                  {eta && isRunning && (
                    <span className="text-[11px] opacity-70">剩余 {eta}</span>
                  )}
                </div>
              </div>
              <Progress value={progress} />
            </div>

            {/* 实时资源指标 */}
            <div className="grid grid-cols-4 gap-2 text-sm">
              <div className="p-2 rounded border text-center">
                <span className="text-muted-foreground text-[10px] flex items-center justify-center gap-0.5">
                  <Activity className="h-2.5 w-2.5" /> Loss
                </span>
                <b className="font-mono text-sm">{loss?.toFixed(4) || "—"}</b>
              </div>
              <div className="p-2 rounded border text-center">
                <span className="text-muted-foreground text-[10px] flex items-center justify-center gap-0.5">
                  <Cpu className="h-2.5 w-2.5" /> 显存
                </span>
                <b className="text-xs">
                  {trainStatus?.gpu_memory_used != null
                    ? `${trainStatus.gpu_memory_used.toFixed(1)}G`
                    : "—"}
                  {trainStatus?.gpu_memory_reserved != null && (
                    <span className="text-muted-foreground text-[10px]">/{trainStatus.gpu_memory_reserved.toFixed(1)}G</span>
                  )}
                </b>
              </div>
              <div className="p-2 rounded border text-center">
                <span className="text-muted-foreground text-[10px] flex items-center justify-center gap-0.5">
                  <HardDrive className="h-2.5 w-2.5" /> 内存
                </span>
                <b className="text-xs">
                  {trainStatus?.system_ram_used != null
                    ? `${trainStatus.system_ram_used.toFixed(1)}GB`
                    : "—"}
                </b>
              </div>
              <div className="p-2 rounded border text-center">
                <span className="text-muted-foreground text-[10px] flex items-center justify-center gap-0.5">
                  <Gauge className="h-2.5 w-2.5" /> 速度
                </span>
                <b className="text-xs">
                  {trainStatus?.training_speed != null
                    ? `${trainStatus.training_speed.toFixed(2)} st/s`
                    : "—"}
                </b>
              </div>
            </div>

            {/* Loss 曲线 */}
            {trainStatus?.loss_history && trainStatus.loss_history.length > 1 && (
              <div>
                <p className="text-[10px] text-muted-foreground mb-1">Loss 变化曲线</p>
                <LossChart data={trainStatus.loss_history} height={140} />
              </div>
            )}

            {/* 日志 */}
            <LogViewer lines={allLogLines} height="200px" />
          </CardContent>
        </Card>
      </div>

      {/* ======== 模型库 ======== */}
      <Card>
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-base font-heading flex items-center gap-2">
            <Brain className="h-4 w-4" />模型库
          </CardTitle>
          <Button variant="ghost" size="sm" onClick={() => refetchModels()}>
            <RefreshCw className="h-3 w-3" />
          </Button>
        </CardHeader>
        <CardContent>
          {(!modelsData?.models || modelsData.models.length === 0) ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              暂无已训练模型。完成微调后会自动出现在这里。
            </p>
          ) : (
            <div className="space-y-2">
              {modelsData.models.map((m) => (
                <div key={m.path} className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg border text-sm gap-2">
                  <div className="min-w-0">
                    <b>{m.name}</b>
                    <span className="text-muted-foreground ml-2 text-xs">
                      {m.base_model && `基于 ${m.base_model}`}
                    </span>
                    {m.description && (
                      <span className="text-muted-foreground ml-2 text-xs">— {m.description}</span>
                    )}
                    <p className="text-xs text-muted-foreground font-mono mt-0.5">{m.path}</p>
                  </div>
                  <div className="flex gap-2 shrink-0">
                    {(m.type === "lora" || m.name?.startsWith("lora_")) && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openMergeDialog(m.path)}
                      >
                        合并
                      </Button>
                    )}
                    {m.type !== "lora" && !m.name?.startsWith("lora_") && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={updateConfigMutation.isPending}
                        onClick={() => handleUseModel(m.path)}
                      >
                        <Download className="h-3 w-3 mr-1" />
                        {updateConfigMutation.isPending ? "配置中..." : "用于翻译"}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ======== 训练历史 ======== */}
      <TrainingHistoryCard onMerge={openMergeDialog} />

      {/* ======== 训练完成摘要 ======== */}
      <TrainingSummaryDialog
        open={showSummary}
        onOpenChange={setShowSummary}
        trainStatus={trainStatus}
        onMerge={() => {
          setShowSummary(false);
          openMergeDialog();
        }}
      />

      {/* ======== 模型合并 ======== */}
      <MergeDialog
        open={mergeOpen}
        onOpenChange={setMergeOpen}
        defaultLoraPath={mergeDefaultPath}
      />
    </div>
  );
}
