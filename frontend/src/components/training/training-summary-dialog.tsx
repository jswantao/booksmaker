"use client";

import { useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LossChart } from "./loss-chart";
import { formatDuration } from "@/lib/utils";
import type { TrainingStatusResponse, LossPoint } from "@/types/api";
import { CheckCircle2, AlertCircle, Clock, BarChart3, Cpu } from "lucide-react";

interface TrainingSummaryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  trainStatus: TrainingStatusResponse | undefined;
  onMerge: () => void;
}

export function TrainingSummaryDialog({
  open,
  onOpenChange,
  trainStatus,
  onMerge,
}: TrainingSummaryDialogProps) {
  const duration = useMemo(() => {
    if (!trainStatus?.started_at) return 0;
    const start = new Date(trainStatus.started_at).getTime();
    const now = Date.now();
    return Math.max(0, Math.floor((now - start) / 1000));
  }, [trainStatus?.started_at, open]);

  const isComplete = trainStatus?.progress !== undefined && trainStatus.progress >= 99;
  const isError = !!trainStatus?.error;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isComplete && <CheckCircle2 className="h-5 w-5 text-green-500" />}
            {isError && <AlertCircle className="h-5 w-5 text-destructive" />}
            {isComplete ? "训练完成" : "训练结束"}
          </DialogTitle>
          <DialogDescription>
            {isError ? trainStatus.error : "模型微调已完成，以下是训练摘要。"}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 py-3">
          <div className="p-3 rounded-lg border text-center">
            <div className="flex items-center justify-center gap-1 text-muted-foreground text-xs mb-1">
              <BarChart3 className="h-3 w-3" /> 最终 Loss
            </div>
            <b className="text-xl font-mono">
              {trainStatus?.loss?.toFixed(4) ?? "—"}
            </b>
          </div>
          <div className="p-3 rounded-lg border text-center">
            <div className="flex items-center justify-center gap-1 text-muted-foreground text-xs mb-1">
              <Clock className="h-3 w-3" /> 训练时长
            </div>
            <b className="text-lg">{formatDuration(duration)}</b>
          </div>
          <div className="p-3 rounded-lg border text-center">
            <div className="flex items-center justify-center gap-1 text-muted-foreground text-xs mb-1">
              <Cpu className="h-3 w-3" /> Epochs
            </div>
            <b className="text-lg">
              {trainStatus?.current_epoch ?? 0}/{trainStatus?.total_epochs ?? 0}
            </b>
          </div>
          <div className="p-3 rounded-lg border text-center">
            <div className="flex items-center justify-center gap-1 text-muted-foreground text-xs mb-1">
              <BarChart3 className="h-3 w-3" /> 总步数
            </div>
            <b className="text-lg font-mono">{trainStatus?.total_steps ?? 0}</b>
          </div>
        </div>

        {trainStatus?.loss_history && trainStatus.loss_history.length > 1 && (
          <div className="pt-1">
            <p className="text-xs text-muted-foreground mb-2">Loss 变化曲线</p>
            <LossChart data={trainStatus.loss_history} height={120} />
          </div>
        )}

        <DialogFooter showCloseButton>
          {isComplete && (
            <Button onClick={onMerge} variant="default">
              合并模型
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
