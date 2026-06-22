"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTrainingHistory } from "@/hooks/use-training";
import { formatDuration } from "@/lib/utils";
import { History, GitMerge } from "lucide-react";
import type { TrainingHistoryRun } from "@/types/api";

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function shortModel(name: string): string {
  const parts = name.split("/");
  return parts[parts.length - 1] || name;
}

interface TrainingHistoryCardProps {
  onMerge?: (loraPath: string) => void;
}

export function TrainingHistoryCard({ onMerge }: TrainingHistoryCardProps) {
  const { data, isLoading } = useTrainingHistory();
  const runs = data?.runs || [];

  return (
    <Card>
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-base font-heading flex items-center gap-2">
          <History className="h-4 w-4" />
          训练历史
        </CardTitle>
        {runs.length > 0 && (
          <span className="text-xs text-muted-foreground">{runs.length} 次训练</span>
        )}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground text-center py-4">加载中...</p>
        ) : runs.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            暂无训练历史记录。完成首次训练后将自动保存。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[100px]">时间</TableHead>
                  <TableHead>基础模型</TableHead>
                  <TableHead className="w-[70px] text-center">Epochs</TableHead>
                  <TableHead className="w-[80px] text-center">Loss</TableHead>
                  <TableHead className="w-[70px] text-center">时长</TableHead>
                  <TableHead className="w-[70px] text-center">状态</TableHead>
                  <TableHead className="w-[80px] text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run: TrainingHistoryRun) => (
                  <TableRow key={run.id}>
                    <TableCell className="text-xs text-muted-foreground font-mono">
                      {formatTime(run.started_at)}
                    </TableCell>
                    <TableCell className="text-xs font-medium">
                      {shortModel(run.base_model)}
                    </TableCell>
                    <TableCell className="text-center text-xs">{run.epochs}</TableCell>
                    <TableCell className="text-center text-xs font-mono">
                      {run.final_loss != null ? run.final_loss.toFixed(4) : "—"}
                    </TableCell>
                    <TableCell className="text-center text-xs">
                      {formatDuration(run.duration_seconds)}
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge
                        variant={run.status === "completed" ? "default" : "destructive"}
                        className="text-[10px]"
                      >
                        {run.status === "completed" ? "完成" : "失败"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {run.status === "completed" && run.output_dir && onMerge && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 px-2 text-xs"
                          onClick={() => onMerge(run.output_dir)}
                        >
                          <GitMerge className="h-3 w-3 mr-1" />
                          合并
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
