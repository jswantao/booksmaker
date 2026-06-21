"use client";

import { cn } from "@/lib/utils";

interface EmptyStateProps {
  message: string;
  className?: string;
}

export function EmptyState({ message, className }: EmptyStateProps) {
  return (
    <div className={cn("flex items-center justify-center p-6 text-sm text-muted-foreground", className)}>
      {message}
    </div>
  );
}
