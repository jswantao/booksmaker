"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { SparklesText } from "@/components/ui/sparkles-text";

type StatusVariant = "ready" | "pending" | "error" | "muted";

interface StatusBadgeProps {
  status: StatusVariant;
  text: string;
  sparkles?: boolean;
}

const variantMap: Record<StatusVariant, "default" | "secondary" | "destructive" | "outline"> = {
  ready: "default",
  pending: "secondary",
  error: "destructive",
  muted: "outline",
};

export function StatusBadge({ status, text, sparkles }: StatusBadgeProps) {
  const content = sparkles && status === "ready" ? (
    <SparklesText sparklesCount={2} className="text-xs">
      {text}
    </SparklesText>
  ) : text;

  return (
    <Badge variant={variantMap[status]} className={cn("text-xs font-medium")}>
      {content}
    </Badge>
  );
}
