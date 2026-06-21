"use client";

import { cn } from "@/lib/utils";
import { CopyButton } from "./copy-button";
import { Loader2 } from "lucide-react";

interface OutputBoxProps {
  content: string;
  isLoading?: boolean;
  className?: string;
  maxHeight?: string;
}

export function OutputBox({ content, isLoading, className, maxHeight = "400px" }: OutputBoxProps) {
  if (isLoading) {
    return (
      <div className={cn("flex items-center justify-center p-8 rounded-lg border border-border bg-muted/30", className)}>
        <Loader2 className="animate-spin mr-2" size={18} />
        <span className="text-muted-foreground text-sm">处理中...</span>
      </div>
    );
  }

  if (!content) {
    return (
      <div className={cn("flex items-center justify-center p-8 rounded-lg border border-border bg-muted/10 text-muted-foreground text-sm", className)}>
        暂无输出
      </div>
    );
  }

  return (
    <div className={cn("relative rounded-lg border border-border bg-muted/10", className)}>
      <div className="absolute top-2 right-2 z-10">
        <CopyButton text={content} />
      </div>
      <div
        className="overflow-auto p-4 font-mono text-sm whitespace-pre-wrap leading-relaxed"
        style={{ maxHeight }}
      >
        {content}
      </div>
    </div>
  );
}
