"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { useTmList, useAddTm, useDeleteTm, useClearTm } from "@/hooks/use-tm";
import type { TmEntry } from "@/types/api";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";

export function TmManager() {
  const { data: tmData } = useTmList();
  const addTm = useAddTm();
  const deleteTm = useDeleteTm();
  const clearTm = useClearTm();

  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [search, setSearch] = useState("");

  const entries = tmData?.results || [];
  const filtered = search
    ? entries.filter((e: TmEntry) =>
        e.source.toLowerCase().includes(search.toLowerCase()) ||
        e.target.toLowerCase().includes(search.toLowerCase()))
    : entries;

  const handleAdd = async () => {
    if (!source.trim() || !target.trim()) { toast.error("原文和译文不能为空"); return; }
    try {
      await addTm.mutateAsync({ source: source.trim(), target: target.trim() });
      setSource(""); setTarget("");
      toast.success("已添加");
    } catch (e) { toast.error("添加失败: " + (e as Error).message); }
  };

  const handleDelete = async (id: number) => {
    try { await deleteTm.mutateAsync(id); } catch {}
  };

  const handleClear = async () => {
    if (!confirm("确定清空所有翻译记忆？")) return;
    try { await clearTm.mutateAsync(); toast.success("已清空"); } catch {}
  };

  return (
    <Card>
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-base font-heading">
          翻译记忆
          <Badge variant="secondary" className="ml-2">{tmData?.total || 0} 条</Badge>
        </CardTitle>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleClear}><Trash2 className="h-3 w-3 mr-1" />清空</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input placeholder="搜索记忆..." value={search} onChange={(e) => setSearch(e.target.value)} className="h-8 text-sm" />
        </div>
        <ScrollArea className="h-[200px]">
          {filtered.length === 0 ? (
            <EmptyState message="暂无翻译记忆" />
          ) : (
            <div className="space-y-1">
              {filtered.map((e: TmEntry) => (
                <div key={e.id} className="flex items-start justify-between p-2 rounded border border-border text-sm">
                  <div className="flex-1 min-w-0">
                    <p className="truncate text-foreground">{e.source}</p>
                    <p className="truncate text-green-700 dark:text-green-400">{e.target}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => handleDelete(e.id)} className="shrink-0">
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
        <div className="flex gap-2 pt-2 border-t border-border">
          <Input placeholder="原文" value={source} onChange={(e) => setSource(e.target.value)} className="h-8 text-sm" />
          <Input placeholder="译文" value={target} onChange={(e) => setTarget(e.target.value)} className="h-8 text-sm" />
          <Button size="sm" onClick={handleAdd} disabled={addTm.isPending}>添加</Button>
        </div>
      </CardContent>
    </Card>
  );
}
