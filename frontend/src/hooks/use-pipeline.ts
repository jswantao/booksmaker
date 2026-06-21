"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  pipelineUpload, pipelineBuildKb, pipelineRun, pipelinePause,
  pipelineResume, pipelineStatus, pipelineResult, pipelineGetMemory,
  pipelineInitMemory, pipelineStitch, pipelineListKbs,
} from "@/lib/api";
import type {
  PipelineRunRequest, PipelineBuildKbRequest, PipelineMemoryInitRequest,
} from "@/types/api";

export function usePipelineUpload() {
  return useMutation({ mutationFn: (formData: FormData) => pipelineUpload(formData) });
}

export function usePipelineBuildKb() {
  return useMutation({ mutationFn: (body: PipelineBuildKbRequest) => pipelineBuildKb(body) });
}

export function usePipelineRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PipelineRunRequest) => pipelineRun(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelineStatus"] }),
  });
}

export function usePipelinePause() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kbName: string) => pipelinePause(kbName),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelineStatus"] }),
  });
}

export function usePipelineResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kbName: string) => pipelineResume(kbName),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelineStatus"] }),
  });
}

export function usePipelineStatus(kbName: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["pipelineStatus", kbName],
    queryFn: () => pipelineStatus(kbName!),
    enabled: enabled && !!kbName,
    refetchInterval: enabled ? 3000 : false,
  });
}

export function usePipelineResult(kbName: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["pipelineResult", kbName],
    queryFn: () => pipelineResult(kbName!),
    enabled: enabled && !!kbName,
    refetchInterval: enabled ? 3000 : false,
  });
}

export function usePipelineMemory(path: string | null) {
  return useQuery({
    queryKey: ["pipelineMemory", path],
    queryFn: () => pipelineGetMemory(path!),
    enabled: !!path,
  });
}

export function usePipelineInitMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PipelineMemoryInitRequest) => pipelineInitMemory(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pipelineMemory"] }),
  });
}

export function usePipelineStitch() {
  return useMutation({ mutationFn: (memoryPath: string) => pipelineStitch(memoryPath) });
}

export function usePipelineKbs() {
  return useQuery({ queryKey: ["pipelineKbs"], queryFn: pipelineListKbs });
}
