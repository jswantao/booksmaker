"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getConfig, saveConfig, getLlmStatus, getEmbeddingStatus, searchModelscopeModels,
} from "@/lib/api";
import type { ConfigRequest } from "@/types/api";

export function useConfig() {
  return useQuery({ queryKey: ["config"], queryFn: getConfig });
}

export function useSaveConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ConfigRequest) => saveConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["config"] });
      qc.invalidateQueries({ queryKey: ["llmStatus"] });
      qc.invalidateQueries({ queryKey: ["embeddingStatus"] });
    },
  });
}

export function useLlmStatus() {
  return useQuery({ queryKey: ["llmStatus"], queryFn: getLlmStatus, refetchInterval: 10_000 });
}

export function useEmbeddingStatus() {
  return useQuery({ queryKey: ["embeddingStatus"], queryFn: getEmbeddingStatus });
}

export function useModelScopeSearch(query: string, maxParams: number) {
  return useQuery({
    queryKey: ["modelscope", query, maxParams],
    queryFn: () => searchModelscopeModels(query, maxParams),
    enabled: false, // manual trigger
  });
}
