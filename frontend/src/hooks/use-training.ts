"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import {
  getTrainingDataStatus, exportTrainingData, startTraining,
  stopTraining, getTrainingStatus, getTrainingLogs, listTrainedModels,
} from "@/lib/api";

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

export function useTrainingStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["trainingStatus"],
    queryFn: getTrainingStatus,
    refetchInterval: enabled ? 2000 : false,
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
