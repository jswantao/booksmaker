"use client";

import { cn } from "@/lib/utils";
import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { TrainingPhase } from "@/types/api";

const PHASES: { key: TrainingPhase; label: string }[] = [
  { key: "downloading", label: "下载模型" },
  { key: "loading_data", label: "加载数据" },
  { key: "loading_model", label: "加载模型" },
  { key: "training", label: "训练中" },
  { key: "evaluating", label: "评估" },
  { key: "saving", label: "保存" },
];

const PHASE_ORDER = PHASES.map((p) => p.key);

function getPhaseState(phaseKey: TrainingPhase, currentPhase: TrainingPhase | undefined) {
  if (!currentPhase || currentPhase === "idle") return "pending";
  if (currentPhase === "complete") return "completed";
  if (currentPhase === "error") {
    const ci = PHASE_ORDER.indexOf(currentPhase);
    const pi = PHASE_ORDER.indexOf(phaseKey);
    if (pi <= ci) return "error";
    return "pending";
  }
  const ci = PHASE_ORDER.indexOf(currentPhase);
  const pi = PHASE_ORDER.indexOf(phaseKey);
  if (pi < ci) return "completed";
  if (pi === ci) return "active";
  return "pending";
}

interface PhaseStepperProps {
  currentPhase?: TrainingPhase;
}

export function PhaseStepper({ currentPhase }: PhaseStepperProps) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto py-1">
      {PHASES.map((phase, i) => {
        const state = getPhaseState(phase.key, currentPhase);
        return (
          <div key={phase.key} className="flex items-center gap-1 shrink-0">
            {i > 0 && (
              <div
                className={cn(
                  "w-3 h-px",
                  state === "completed" ? "bg-green-500" : "bg-muted-foreground/30"
                )}
              />
            )}
            <div
              className={cn(
                "flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] transition-colors",
                state === "active" && "bg-primary/10 text-primary font-medium",
                state === "completed" && "text-green-600 dark:text-green-400",
                state === "pending" && "text-muted-foreground/60",
                state === "error" && "text-destructive"
              )}
            >
              {state === "active" && <Loader2 className="h-3 w-3 animate-spin" />}
              {state === "completed" && <CheckCircle2 className="h-3 w-3" />}
              {state === "pending" && <Circle className="h-3 w-3 opacity-40" />}
              {state === "error" && <Circle className="h-3 w-3" />}
              <span className="whitespace-nowrap">{phase.label}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
