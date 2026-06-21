"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchTmList, addTmPair, deleteTmEntry, clearTmAll, searchTm, reindexTm, fetchKnowledge } from "@/lib/api";

export function useTmList() {
  return useQuery({ queryKey: ["tmList"], queryFn: () => fetchTmList(100), refetchInterval: 15_000 });
}

export function useAddTm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ source, target }: { source: string; target: string }) => addTmPair(source, target),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tmList"] }),
  });
}

export function useDeleteTm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteTmEntry(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tmList"] }),
  });
}

export function useClearTm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: clearTmAll,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tmList"] }),
  });
}

export function useSearchTm() {
  return useMutation({ mutationFn: (query: string) => searchTm(query) });
}

export function useReindexTm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: reindexTm,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tmList"] }),
  });
}

export function useKnowledge() {
  return useQuery({ queryKey: ["knowledge"], queryFn: fetchKnowledge, refetchInterval: 15_000 });
}
