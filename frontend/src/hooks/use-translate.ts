"use client";

import { useMutation } from "@tanstack/react-query";
import { callTranslate, callEpubReplace } from "@/lib/api";
import type { TranslateRequest, EpubReplaceRequest } from "@/types/api";

export function useTranslate() {
  return useMutation({ mutationFn: (body: TranslateRequest) => callTranslate(body) });
}

export function useEpubReplace() {
  return useMutation({ mutationFn: (body: EpubReplaceRequest) => callEpubReplace(body) });
}
