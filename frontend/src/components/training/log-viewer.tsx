"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, ArrowDown, ArrowDownUp } from "lucide-react";
import { cn } from "@/lib/utils";

interface LogViewerProps {
  lines: string[];
  height?: string;
}

function classifyLine(line: string): "error" | "warn" | "success" | "info" {
  const ll = line.toLowerCase();
  if (/error|❌|异常|失败|traceback/.test(ll)) return "error";
  if (/warning|warn|⚠️/.test(ll)) return "warn";
  if (/✅|完成|成功/.test(ll)) return "success";
  return "info";
}

const LINE_COLORS = {
  error: "text-red-400",
  warn: "text-yellow-400",
  success: "text-emerald-400",
  info: "text-green-400/70",
} as const;

export function LogViewer({ lines, height = "220px" }: LogViewerProps) {
  const [search, setSearch] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    if (!search.trim()) return lines;
    const q = search.toLowerCase();
    return lines.filter((l) => l.toLowerCase().includes(q));
  }, [lines, search]);

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [filtered.length, autoScroll]);

  return (
    <div className="space-y-1.5">
      <div className="flex gap-1.5 items-center">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索日志..."
            className="h-7 pl-7 text-xs font-mono bg-black/80 border-border/50 text-green-300 placeholder:text-muted-foreground/50"
          />
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 w-7 p-0"
          onClick={() => setAutoScroll(!autoScroll)}
          title={autoScroll ? "关闭自动滚动" : "开启自动滚动"}
        >
          {autoScroll ? (
            <ArrowDown className="h-3 w-3 text-primary" />
          ) : (
            <ArrowDownUp className="h-3 w-3 text-muted-foreground" />
          )}
        </Button>
      </div>
      <ScrollArea style={{ height }} className="rounded border bg-black">
        <div className="p-2 font-mono text-[11px] leading-5">
          {filtered.length === 0 && (
            <span className="text-gray-500">
              {search ? "无匹配日志" : "等待训练输出..."}
            </span>
          )}
          {filtered.map((line, i) => (
            <div
              key={i}
              className={cn(
                "whitespace-pre-wrap break-all",
                LINE_COLORS[classifyLine(line)]
              )}
            >
              {line}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </ScrollArea>
    </div>
  );
}
