"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useStartMerge, useMergeStatus, useTrainedModels, useAvailableBaseModels } from "@/hooks/use-training";
import { toast } from "sonner";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";

interface MergeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultLoraPath?: string;
}

export function MergeDialog({ open, onOpenChange, defaultLoraPath }: MergeDialogProps) {
  const { data: modelsData } = useTrainedModels();
  const { data: availableModels } = useAvailableBaseModels();
  const startMerge = useStartMerge();
  const [merging, setMerging] = useState(false);
  const { data: mergeStatus } = useMergeStatus(merging);

  const defaultBaseModel = availableModels?.recommended?.[0]?.id || "Tencent-Hunyuan/Hy-MT2-1.8B";
  const [selectedLora, setSelectedLora] = useState(defaultLoraPath || "");
  const [baseModel, setBaseModel] = useState(defaultBaseModel);
  const [outputName, setOutputName] = useState(
    `history-translator-${new Date().toISOString().slice(0, 10)}`
  );

  useEffect(() => {
    if (defaultLoraPath) setSelectedLora(defaultLoraPath);
  }, [defaultLoraPath]);

  useEffect(() => {
    if (mergeStatus && !mergeStatus.running && merging) {
      setMerging(false);
      if (mergeStatus.error) {
        toast.error(mergeStatus.error);
      } else if (mergeStatus.done) {
        toast.success("模型合并完成！");
        onOpenChange(false);
      }
    }
  }, [mergeStatus, merging]);

  const loraModels = (modelsData?.models || []).filter(
    (m) => m.type === "lora" || m.name?.startsWith("lora_")
  );

  const handleMerge = async () => {
    if (!selectedLora) {
      toast.error("请选择 LoRA 适配器");
      return;
    }
    try {
      const r = await startMerge.mutateAsync({
        lora_path: selectedLora,
        base_model: baseModel,
        output_name: outputName,
      });
      if (r.success) {
        setMerging(true);
        toast.success("合并已启动");
      } else {
        toast.error(r.error || "启动合并失败");
      }
    } catch {
      toast.error("合并请求失败");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>合并 LoRA 模型</DialogTitle>
          <DialogDescription>
            将训练好的 LoRA 适配器合并到基础模型中，生成可独立使用的完整模型。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div>
            <label className="text-xs font-medium">LoRA 适配器</label>
            {loraModels.length > 0 ? (
              <Select value={selectedLora} onValueChange={(v) => setSelectedLora(v || "")}>
                <SelectTrigger className="mt-1 h-9 text-sm">
                  <SelectValue placeholder="选择 LoRA 适配器..." />
                </SelectTrigger>
                <SelectContent>
                  {loraModels.map((m) => (
                    <SelectItem key={m.path} value={m.path}>
                      {m.name} — {m.description}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <Input
                value={selectedLora}
                onChange={(e) => setSelectedLora(e.target.value)}
                placeholder="输入 LoRA 适配器路径..."
                className="mt-1 h-9 text-sm"
              />
            )}
          </div>

          <div>
            <label className="text-xs font-medium">基础模型</label>
            <Select value={baseModel} onValueChange={(v) => setBaseModel(v || defaultBaseModel)}>
              <SelectTrigger className="mt-1 h-9 text-sm">
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
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="text-xs font-medium">输出名称</label>
            <Input
              value={outputName}
              onChange={(e) => setOutputName(e.target.value)}
              placeholder="history-translator"
              className="mt-1 h-9 text-sm"
            />
            <p className="text-[11px] text-muted-foreground mt-0.5">
              模型将保存到 models/{outputName}/
            </p>
          </div>

          {merging && (
            <div className="space-y-2 pt-2 border-t">
              <div className="flex items-center gap-2">
                {mergeStatus?.done ? (
                  <Badge variant="default" className="gap-1">
                    <CheckCircle2 className="h-3 w-3" /> 完成
                  </Badge>
                ) : mergeStatus?.error ? (
                  <Badge variant="destructive" className="gap-1">
                    <AlertCircle className="h-3 w-3" /> 错误
                  </Badge>
                ) : (
                  <Badge variant="secondary" className="gap-1 animate-pulse">
                    <Loader2 className="h-3 w-3 animate-spin" /> 合并中...
                  </Badge>
                )}
              </div>
              {mergeStatus?.log_lines && mergeStatus.log_lines.length > 0 && (
                <ScrollArea className="h-[120px] rounded border bg-black">
                  <div className="p-2 font-mono text-[11px] text-green-400/70 leading-5">
                    {mergeStatus.log_lines.map((line, i) => (
                      <div key={i} className="whitespace-pre-wrap break-all">
                        {line}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleMerge} disabled={merging || !selectedLora}>
            {merging ? (
              <>
                <Loader2 className="h-3 w-3 mr-1 animate-spin" /> 合并中...
              </>
            ) : (
              "开始合并"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
