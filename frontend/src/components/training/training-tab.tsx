"use client";

import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ShinyButton } from "@/components/ui/shiny-button";
import {
  useTrainingData, useExportTrainingData, useStartTraining,
  useStopTraining, useTrainingStatus, useTrainingLogs, useTrainedModels,
} from "@/hooks/use-training";
import { loadSeedData as apiLoadSeed, importParagraphPairs } from "@/lib/api";
import { toast } from "sonner";
import { Database, Zap, Square, Play, Download, Brain, Cpu, RefreshCw, Terminal, Upload, Sparkles, Plus, X } from "lucide-react";

const BASE_MODELS = [
  { id: "Tencent-Hunyuan/Hy-MT2-1.8B", label: "Hy-MT2-1.8B (混元翻译二代 ⭐推荐)" },
  { id: "Tencent-Hunyuan/Hunyuan-MT-7B", label: "Hunyuan-MT-7B (混元翻译一代)" },
  { id: "Qwen/Qwen2-7B-Instruct", label: "Qwen2-7B (通用)" },
  { id: "Qwen/Qwen2.5-1.5B-Instruct", label: "Qwen2.5-1.5B (轻量)" },
  { id: "Qwen/Qwen2.5-3B-Instruct", label: "Qwen2.5-3B" },
];

export function TrainingTab() {
  // Data
  const { data: dataStatus, refetch: refetchData } = useTrainingData();
  const exportData = useExportTrainingData();
  const [dataOutput, setDataOutput] = useState("data/train.jsonl");

  // Training config
  const [baseModel, setBaseModel] = useState("Tencent-Hunyuan/Hy-MT2-1.8B");
  const [epochs, setEpochs] = useState(3);
  const [batchSize, setBatchSize] = useState(1);
  const [gradAccum, setGradAccum] = useState(8);
  const [learningRate, setLearningRate] = useState(2e-4);
  const [loraR, setLoraR] = useState(16);
  const [loraAlpha, setLoraAlpha] = useState(32);

  // Training state
  const startTraining = useStartTraining();
  const stopTraining = useStopTraining();
  const [isRunning, setIsRunning] = useState(false);
  const { data: trainStatus } = useTrainingStatus(isRunning || startTraining.isPending);
  const [logSince, setLogSince] = useState(0);
  const { data: logData } = useTrainingLogs(isRunning, logSince);
  const { data: modelsData, refetch: refetchModels } = useTrainedModels();
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (trainStatus?.running) setIsRunning(true);
    else if (trainStatus && !trainStatus.running && isRunning) {
      setIsRunning(false);
      if (trainStatus.error) toast.error(trainStatus.error);
      else if (trainStatus.progress >= 99) toast.success("训练完成!");
    }
  }, [trainStatus, isRunning]);

  useEffect(() => {
    if (logData?.lines?.length) {
      setLogSince(logData.total);
    }
  }, [logData]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logData?.lines]);

  // 翻译对队列 (用户友好的表单录入)
  const [queue, setQueue] = useState<Array<{ source: string; target: string }>>([]);
  const [srcInput, setSrcInput] = useState("");
  const [tgtInput, setTgtInput] = useState("");
  const [importingSeed, setImportingSeed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [showBatch, setShowBatch] = useState(false);

  // 从纯文本清洗 HTML 标签
  const cleanHtml = (text: string) => text.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();

  const addToQueue = () => {
    const s = cleanHtml(srcInput).trim();
    const t = cleanHtml(tgtInput).trim();
    if (s.length < 10) { toast.error("原文太短（至少10字符）"); return; }
    if (t.length < 5) { toast.error("译文太短（至少5字符）"); return; }
    const dup = queue.find((q) => q.source === s);
    if (dup) { toast.error("此翻译对已在队列中"); return; }
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

  // 批量粘贴：自动拆分多对
  const [batchText, setBatchText] = useState("");
  const handleBatchPaste = () => {
    const text = batchText.trim();
    if (!text) return;
    let added = 0;
    // 尝试 JSON 格式
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
      // 尝试用空行分隔的纯文本格式 (原文\n译文\n\n原文\n译文...)
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
    } catch (e) { toast.error("导出失败"); }
  };

  const handleStart = async () => {
    try {
      const r = await startTraining.mutateAsync({
        base_model: baseModel, data_path: dataOutput, output_dir: "./lora_output",
        epochs, batch_size: batchSize, gradient_accumulation: gradAccum,
        learning_rate: learningRate, lora_r: loraR, lora_alpha: loraAlpha, use_4bit: true,
      });
      if (r.success) { setIsRunning(true); setLogSince(0); toast.success("训练已启动"); }
      else toast.error(r.error);
    } catch (e) { toast.error("启动失败"); }
  };

  const handleStop = async () => {
    try { await stopTraining.mutateAsync(); setIsRunning(false); toast.success("已发送停止信号"); }
    catch { toast.error("停止失败"); }
  };

  const handleUseModel = (path: string) => {
    const input = document.getElementById("localTranslateModel") as HTMLInputElement;
    if (input) { input.value = path; toast.success(`已填入: ${path}`); }
    else { navigator.clipboard.writeText(path); toast.success(`路径已复制: ${path}`); }
  };

  const progress = isRunning ? (trainStatus?.progress || 0) : 0;
  const loss = trainStatus?.loss;
  const error = trainStatus?.error;

  return (
    <div className="space-y-6">
      {/* ---- 数据准备 ---- */}
      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-lg font-heading flex items-center gap-2"><Database className="h-5 w-5" />数据准备</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
            <div className="p-3 rounded-lg border"><p className="text-muted-foreground text-xs">翻译记忆</p><b className="text-lg">{dataStatus?.tm_entries ?? "?"}</b><span className="text-xs ml-1">条</span></div>
            <div className="p-3 rounded-lg border"><p className="text-muted-foreground text-xs">共享术语</p><b className="text-lg">{dataStatus?.shared_terms ?? "?"}</b><span className="text-xs ml-1">条</span></div>
            <div className="p-3 rounded-lg border"><p className="text-muted-foreground text-xs">训练样本</p><b className="text-lg">{dataStatus?.train_samples ?? "?"}</b><span className="text-xs ml-1">条</span></div>
            <div className="p-3 rounded-lg border flex items-center justify-center">
              <Badge variant={dataStatus?.ready ? "default" : "secondary"}>{dataStatus?.ready ? "可训练" : "数据不足"}</Badge>
            </div>
          </div>
          <div className="flex gap-2 mb-3">
            <Input value={dataOutput} onChange={(e) => setDataOutput(e.target.value)} placeholder="data/train.jsonl" className="h-8 text-sm flex-1" />
            <Button size="sm" variant="outline" onClick={handleLoadSeed} disabled={importingSeed}>
              <Sparkles className="h-3 w-3 mr-1" />{importingSeed ? "导入中..." : "加载种子数据"}
            </Button>
            <Button size="sm" onClick={handleExport} disabled={exportData.isPending}>
              <Download className="h-3 w-3 mr-1" />{exportData.isPending ? "导出中..." : "导出 TM 数据"}
            </Button>
          </div>
          {/* 翻译对表单录入 */}
          <div className="mt-4 pt-3 border-t">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium">录入翻译对</span>
              <Badge variant="secondary" className="text-xs">{queue.length} 条待提交</Badge>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">原文 (English)</label>
                <textarea className="w-full h-[80px] mt-1 p-2 border rounded text-sm resize-y font-sans"
                  placeholder="粘贴英文原文... HTML 标签会自动清理"
                  value={srcInput} onChange={(e) => setSrcInput(e.target.value)} />
              </div>
              <div>
                <label className="text-xs font-medium text-muted-foreground">译文 (中文)</label>
                <textarea className="w-full h-[80px] mt-1 p-2 border rounded text-sm resize-y font-sans"
                  placeholder="粘贴中文译文..."
                  value={tgtInput} onChange={(e) => setTgtInput(e.target.value)} />
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
                <textarea className="w-full h-[80px] p-2 border rounded text-xs font-mono resize-y"
                  placeholder={'支持 JSON: [{"source":"...","target":"..."}]\n或纯文本: 原文\\n译文\\n\\n原文\\n译文'}
                  value={batchText} onChange={(e) => setBatchText(e.target.value)} />
                <Button size="sm" variant="ghost" onClick={handleBatchPaste} className="mt-1">识别并导入</Button>
              </div>
            )}
            {/* 队列预览 */}
            {queue.length > 0 && (
              <ScrollArea className="h-[120px] mt-2 border rounded">
                <div className="p-2 space-y-1">
                  {queue.map((q, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs p-1.5 rounded hover:bg-muted/50 group">
                      <span className="text-muted-foreground shrink-0">{i + 1}.</span>
                      <div className="flex-1 min-w-0">
                        <p className="truncate font-medium">{q.source.substring(0, 80)}</p>
                        <p className="truncate text-green-700 dark:text-green-400">{q.target.substring(0, 80)}</p>
                      </div>
                      <Button variant="ghost" size="sm" className="h-5 w-5 p-0 opacity-0 group-hover:opacity-100 shrink-0"
                        onClick={() => removeFromQueue(i)}><X className="h-3 w-3" /></Button>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ---- 训练配置 + 控制 ---- */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card className="xl:col-span-1">
          <CardHeader className="pb-2"><CardTitle className="text-base font-heading flex items-center gap-2"><Brain className="h-4 w-4" />训练参数</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div><label className="text-xs font-medium">基础模型</label>
              <Select value={baseModel} onValueChange={(v) => setBaseModel(v || BASE_MODELS[0].id)}>
                <SelectTrigger className="mt-1 h-8 text-sm"><SelectValue /></SelectTrigger>
                <SelectContent>{BASE_MODELS.map((m) => <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>)}</SelectContent>
              </Select></div>
            <div className="grid grid-cols-2 gap-2">
              <div><label className="text-xs font-medium">Epochs</label><Input type="number" value={epochs} onChange={(e) => setEpochs(+e.target.value)} min={1} max={10} className="mt-1 h-8 text-sm" /></div>
              <div><label className="text-xs font-medium">Batch Size</label><Input type="number" value={batchSize} onChange={(e) => setBatchSize(+e.target.value)} min={1} max={8} className="mt-1 h-8 text-sm" /></div>
              <div><label className="text-xs font-medium">Grad Accum</label><Input type="number" value={gradAccum} onChange={(e) => setGradAccum(+e.target.value)} min={1} max={32} className="mt-1 h-8 text-sm" /></div>
              <div><label className="text-xs font-medium">LR</label><Input type="number" value={learningRate} onChange={(e) => setLearningRate(+e.target.value)} step={0.0001} min={1e-5} max={1e-3} className="mt-1 h-8 text-sm font-mono" /></div>
              <div><label className="text-xs font-medium">LoRA r</label><Input type="number" value={loraR} onChange={(e) => setLoraR(+e.target.value)} min={4} max={64} className="mt-1 h-8 text-sm" /></div>
              <div><label className="text-xs font-medium">LoRA α</label><Input type="number" value={loraAlpha} onChange={(e) => setLoraAlpha(+e.target.value)} min={8} max={128} className="mt-1 h-8 text-sm" /></div>
            </div>
            <div className="flex gap-2 pt-1">
              {!isRunning ? (
                <ShinyButton onClick={handleStart} className="flex-1">
                  <Zap className="h-3 w-3 mr-1" />{startTraining.isPending ? "启动中..." : "开始训练"}
                </ShinyButton>
              ) : (
                <Button variant="destructive" onClick={handleStop} className="flex-1"><Square className="h-3 w-3 mr-1" />停止训练</Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* ---- 进度监控 ---- */}
        <Card className="xl:col-span-2">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-base font-heading flex items-center gap-2"><Terminal className="h-4 w-4" />训练监控</CardTitle>
            <div className="flex gap-2 items-center">
              {isRunning && <Badge variant="default" className="animate-pulse">运行中</Badge>}
              {!isRunning && !error && <Badge variant="secondary">空闲</Badge>}
              {error && <Badge variant="destructive">异常</Badge>}
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <div className="flex justify-between text-xs text-muted-foreground mb-1">
                <span>Epoch {trainStatus?.current_epoch || 0}/{trainStatus?.total_epochs || 0}</span>
                <span>{trainStatus?.step || 0}/{trainStatus?.total_steps || 0} steps</span>
                <span>{progress.toFixed(0)}%</span>
              </div>
              <Progress value={progress} />
            </div>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div className="p-2 rounded border text-center"><span className="text-muted-foreground text-xs">Loss</span><br /><b className="font-mono">{loss?.toFixed(4) || "—"}</b></div>
              <div className="p-2 rounded border text-center"><span className="text-muted-foreground text-xs">显存</span><br /><b><Cpu className="h-3 w-3 inline" /> ~8GB</b></div>
              <div className="p-2 rounded border text-center"><span className="text-muted-foreground text-xs">输出</span><br /><b className="text-xs">lora_output/</b></div>
            </div>
            <ScrollArea className="h-[200px] rounded border bg-black text-green-400 p-3 font-mono text-xs">
              {(!logData?.lines || logData.lines.length === 0) && (
                <span className="text-gray-500">等待训练输出...</span>
              )}
              {logData?.lines?.map((line, i) => (
                <div key={i} className="leading-5 whitespace-pre-wrap break-all">{line}</div>
              ))}
              <div ref={logEndRef} />
            </ScrollArea>
          </CardContent>
        </Card>
      </div>

      {/* ---- 模型库 ---- */}
      <Card>
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-base font-heading flex items-center gap-2"><Brain className="h-4 w-4" />模型库</CardTitle>
          <Button variant="ghost" size="sm" onClick={() => refetchModels()}><RefreshCw className="h-3 w-3" /></Button>
        </CardHeader>
        <CardContent>
          {(!modelsData?.models || modelsData.models.length === 0) ? (
            <p className="text-sm text-muted-foreground py-4 text-center">暂无已训练模型。完成微调后会自动出现在这里。</p>
          ) : (
            <div className="space-y-2">
              {modelsData.models.map((m) => (
                <div key={m.path} className="flex items-center justify-between p-3 rounded-lg border text-sm">
                  <div>
                    <b>{m.name}</b>
                    <span className="text-muted-foreground ml-2 text-xs">{m.base_model && `基于 ${m.base_model}`}</span>
                    {m.description && <span className="text-muted-foreground ml-2 text-xs">— {m.description}</span>}
                    <p className="text-xs text-muted-foreground font-mono mt-0.5">{m.path}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => handleUseModel(m.path)}>
                    <Download className="h-3 w-3 mr-1" />使用此模型
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
