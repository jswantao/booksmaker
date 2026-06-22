"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useTerms, useAddTerm, useDeleteTerm } from "@/hooks/use-terminology";
import { toast } from "sonner";
import { Plus, Search, X } from "lucide-react";

export function TerminologySection() {
  const [enTerm, setEnTerm] = useState("");
  const [zhTerm, setZhTerm] = useState("");
  const [search, setSearch] = useState("");
  const { data } = useTerms(search || undefined);
  const addTerm = useAddTerm();
  const deleteTerm = useDeleteTerm();

  const terms = data?.terms || {};

  const handleAdd = async () => {
    if (!enTerm.trim() || !zhTerm.trim()) return;
    try {
      await addTerm.mutateAsync({ en: enTerm.trim(), zh: zhTerm.trim() });
      setEnTerm(""); setZhTerm("");
    } catch (e) { toast.error("添加失败"); }
  };

  const handleDelete = async (en: string) => {
    try { await deleteTerm.mutateAsync(en); } catch {}
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">术语管理</span>
        <span className="text-xs text-muted-foreground">({Object.keys(terms).length} 条)</span>
      </div>
      <div className="flex gap-2">
        <Input placeholder="英文术语" value={enTerm} onChange={(e) => setEnTerm(e.target.value)} className="h-7 text-xs" />
        <Input placeholder="中文译名" value={zhTerm} onChange={(e) => setZhTerm(e.target.value)} className="h-7 text-xs" />
        <Button size="sm" onClick={handleAdd} className="h-7 text-xs px-2"><Plus className="h-3 w-3" /></Button>
      </div>
      <div className="flex gap-2">
        <Input placeholder="搜索术语..." value={search} onChange={(e) => setSearch(e.target.value)} className="h-7 text-xs" />
      </div>
      <ScrollArea className="h-[120px]">
        <div className="space-y-1">
          {Object.entries(terms).slice(0, 30).map(([en, zh]) => (
            <div key={en} className="flex justify-between items-center text-xs p-1 border-b border-border">
              <span><b>{en}</b> → {zh}</span>
              <Button variant="ghost" size="sm" className="h-5 w-5 p-0 shrink-0" onClick={() => handleDelete(en)}>
                <X className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
