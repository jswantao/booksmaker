"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchKbList, createKb, updateKb, deleteKb, uploadToKb,
  createGroup, updateGroup, deleteGroup,
} from "@/lib/api";
import type { KbCreateRequest, KbUpdateRequest, KbGroupRequest } from "@/types/api";

export function useKbList() {
  return useQuery({ queryKey: ["kbList"], queryFn: fetchKbList, refetchInterval: 15_000 });
}

export function useCreateKb() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: KbCreateRequest) => createKb(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kbList"] }),
  });
}

export function useUpdateKb() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: KbUpdateRequest }) => updateKb(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kbList"] }),
  });
}

export function useDeleteKb() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteKb(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kbList"] }),
  });
}

export function useUploadToKb() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kbId, formData }: { kbId: string; formData: FormData }) => uploadToKb(kbId, formData),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kbList"] }),
  });
}

export function useCreateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: KbGroupRequest) => createGroup(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kbList"] }),
  });
}

export function useUpdateGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: KbGroupRequest }) => updateGroup(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kbList"] }),
  });
}

export function useDeleteGroup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteGroup(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["kbList"] }),
  });
}
