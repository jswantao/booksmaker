"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listTerms, addTerm, deleteTerm } from "@/lib/api";

export function useTerms(search?: string) {
  return useQuery({ queryKey: ["terms", search], queryFn: () => listTerms(search) });
}

export function useAddTerm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ en, zh }: { en: string; zh: string }) => addTerm(en, zh),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["terms"] }),
  });
}

export function useDeleteTerm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (en: string) => deleteTerm(en),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["terms"] }),
  });
}
