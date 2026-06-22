"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getTrainingDataStatus, exportTrainingData, startTraining,
  stopTraining, getTrainingStatus, getTrainingLogs, listTrainedModels,
  checkTrainingEnv, getTrainingHistory, startMerge, getMergeStatus,
  getAvailableBaseModels, updateConfig,
} from "@/lib/api";
import type { TrainingPhase, ConfigRequest } from "@/types/api";

export function useTrainingData() {
  return useQuery({ queryKey: ["trainingData"], queryFn: getTrainingDataStatus });
}

export function useExportTrainingData() {
  return useMutation({
    mutationFn: (body: { tm_db?: string; memory_dir?: string; output?: string }) =>
      exportTrainingData(body),
  });
}

export function useStartTraining() {
  return useMutation({ mutationFn: startTraining });
}

export function useStopTraining() {
  return useMutation({ mutationFn: stopTraining });
}

/** 根据训练阶段动态调整轮询间隔 */
function phaseInterval(phase: TrainingPhase | undefined, enabled: boolean): number | false {
  if (!enabled) return false;
  if (!phase || phase === "idle") return 3000;
  if (phase === "downloading") return 5000;
  if (phase === "complete" || phase === "error") return false;
  return 2000; // training, evaluating, saving, loading_*
}

export function useTrainingStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["trainingStatus"],
    queryFn: getTrainingStatus,
    refetchInterval: (query) => {
      if (!enabled) return false;
      const data = query.state.data;
      if (!data?.running) return false;
      return phaseInterval(data.phase, true);
    },
  });
}

export function useTrainingLogs(enabled: boolean, since: number) {
  return useQuery({
    queryKey: ["trainingLogs", since],
    queryFn: () => getTrainingLogs(since),
    refetchInterval: enabled ? 2000 : false,
  });
}

export function useTrainedModels() {
  return useQuery({ queryKey: ["trainedModels"], queryFn: listTrainedModels });
}

export function useTrainingEnvCheck() {
  return useQuery({ queryKey: ["trainingEnv"], queryFn: checkTrainingEnv });
}

export function useTrainingHistory() {
  return useQuery({ queryKey: ["trainingHistory"], queryFn: getTrainingHistory });
}

export function useStartMerge() {
  return useMutation({ mutationFn: startMerge });
}

export function useMergeStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["mergeStatus"],
    queryFn: getMergeStatus,
    refetchInterval: enabled ? 3000 : false,
  });
}

export function useAvailableBaseModels() {
  return useQuery({
    queryKey: ["availableBaseModels"],
    queryFn: getAvailableBaseModels,
    staleTime: 30_000,
  });
}

export function useUpdateConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<ConfigRequest>) => updateConfig(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["llmStatus"] });
      queryClient.invalidateQueries({ queryKey: ["config"] });
    },
  });
}
