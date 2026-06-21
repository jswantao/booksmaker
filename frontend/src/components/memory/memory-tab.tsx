"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DotPattern } from "@/components/ui/dot-pattern";
import { EmptyState } from "@/components/shared/empty-state";
import { CopyButton } from "@/components/shared/copy-button";
import { usePipelineMemory, usePipelineInitMemory } from "@/hooks/use-pipeline";
import { Search, Download, Upload as UploadIcon, Rocket } from "lucide-react";
import { toast } from "sonner";
import { debounce } from "@/lib/utils";

type TermEntry = { en: string; zh: string; source: string };

export function MemoryTab() {
  const [memoryPath, setMemoryPath] = useState("");
  const [pathInput, setPathInput] = useState("");
  const [autoPath, setAutoPath] = useState("");
  const { data, refetch } = usePipelineMemory(memoryPath || null);
  const initMemory = usePipelineInitMemory();
  const [terms, setTerms] = useState<TermEntry[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "seed" | "auto">("all");

  // Auto-detect memory path from localStorage or book name input
  useEffect(() => {
    const stored = typeof window !== "undefined" ? localStorage.getItem("lastMemoryPath") : null;
    if (stored) setAutoPath(stored);
    // Also try to read from translate book input in the workspace
    const bookInput = typeof document !== "undefined" ? document.getElementById("translateBook") : null;
    if (bookInput && (bookInput as HTMLInputElement).value) {
      const book = (bookInput as HTMLInputElement).value.trim();
      const derived = `memory/${book.replace(/[\\/:*?"<>|]/g, "_")}_memory.json`;
      setAutoPath(derived);
    }
  }, []);

  useEffect(() => {
    if (data?.success) {
      const raw = data.terms || data.terminology || {};
      let arr: TermEntry[];
      if (Array.isArray(raw)) {
        arr = raw.map((t: any) => ({
          en: t.en || t.english || "",
          zh: t.zh || t.target || t.chinese || (typeof t === "object" && t.translation ? t.translation : ""),
          source: t.source || t.source_type || t.source_tag || "seed",
        }));
      } else if (typeof raw === "object") {
        arr = Object.entries(raw as Record<string, unknown>).map(([en, val]) => ({
          en, zh: typeof val === "string" ? val : (val as any)?.translation || (val as any)?.target || "",
          source: typeof val === "object" ? (val as any)?.source_type || "seed" : "seed",
        }));
      } else { arr = []; }
      setTerms(arr);
      if (memoryPath) localStorage.setItem("lastMemoryPath", memoryPath);
    }
  }, [data, memoryPath]);

  const filtered = terms.filter((t) => {
    if (filter === "seed" && t.source !== "seed") return false;
    if (filter === "auto" && t.source !== "auto") return false;
    if (search) return t.en.toLowerCase().includes(search.toLowerCase()) || t.zh.includes(search);
    return true;
  });

  const seedCount = terms.filter((t) => t.source === "seed").length;
  const autoCount = terms.filter((t) => t.source === "auto").length;
  const projectName = data?.project_name || memoryPath.replace(/^memory[\\/]/, "").replace(/_memory\.json$/, "").replace(/[\\/]/g, " ") || "未知";

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const debouncedSearch = useCallback(
    debounce(((val: string) => setSearch(val)) as (...args: unknown[]) => void, 200),
    []
  );

  const handleExport = () => {
    const dict: Record<string, string> = {};
    terms.forEach((t) => { dict[t.en] = t.zh; });
    const blob = new Blob([JSON.stringify(dict, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "terms.json"; a.click();
    URL.revokeObjectURL(url);
    toast.success(`导出 ${terms.length} 条术语`);
  };

  const handleImport = () => {
    const input = document.createElement("input"); input.type = "file"; input.accept = ".json";
    input.onchange = async () => {
      const file = input.files?.[0]; if (!file) return;
      try {
        const text = await file.text(); const parsed = JSON.parse(text);
        const newTerms: TermEntry[] = Array.isArray(parsed)
          ? parsed.map((t: any) => ({ en: t.en || t[0] || "", zh: t.zh || t.target || t[1] || "", source: "seed" }))
          : Object.entries(parsed).map(([en, zh]) => ({ en, zh: zh as string, source: "seed" }));
        const existing = new Set(terms.map((t) => t.en.toLowerCase()));
        const added = newTerms.filter((t) => !existing.has(t.en.toLowerCase()));
        const skipped = newTerms.length - added.length;
        setTerms([...terms, ...added]);
        toast.success(`导入 ${added.length} 条` + (skipped > 0 ? `，跳过 ${skipped} 条重复` : ""));
      } catch { toast.error("导入失败: 无效JSON"); }
    };
    input.click();
  };

  const handleInit = async () => {
    if (!memoryPath) { toast.error("请输入记忆库路径"); return; }
    if (!confirm("确定初始化记忆库？这将清空现有数据")) return;
    try {
      await initMemory.mutateAsync({ memory_path: memoryPath, project: projectName });
      setTerms([]); toast.success("已初始化");
    } catch { toast.error("初始化失败"); }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Input placeholder="记忆库路径" value={pathInput} onChange={(e) => setPathInput(e.target.value)}
              className="flex-1 max-w-md text-xs" />
            {autoPath && !pathInput && <span className="text-xs text-muted-foreground">自动检测: {autoPath}</span>}
            <Button size="sm" onClick={() => { setMemoryPath(pathInput || autoPath); setTimeout(refetch, 100); }}>加载</Button>
            <Button variant="outline" size="sm" onClick={handleExport}><Download className="h-3 w-3 mr-1" />导出</Button>
            <Button variant="outline" size="sm" onClick={handleImport}><UploadIcon className="h-3 w-3 mr-1" />导入</Button>
            <Button variant="outline" size="sm" onClick={handleInit}><Rocket className="h-3 w-3 mr-1" />初始化</Button>
          </div>
          {projectName !== "未知" && <p className="text-xs text-muted-foreground mt-1">项目: {projectName}</p>}
        </CardHeader>
      </Card>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "术语总数", value: terms.length },
          { label: "种子术语", value: seedCount },
          { label: "自动提取", value: autoCount },
          { label: "完成章节", value: data?.completed_chapters || 0 },
        ].map((stat) => (
          <Card key={stat.label} className="relative overflow-hidden">
            <DotPattern className="absolute inset-0 opacity-[0.03]" />
            <CardContent className="relative p-4 text-center">
              <p className="text-xs text-muted-foreground">{stat.label}</p>
              <p className="text-2xl font-bold font-heading text-primary">{stat.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 max-w-xs">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input placeholder="搜索术语..." onChange={(e) => debouncedSearch(e.target.value)} className="pl-8 h-8 text-sm" />
            </div>
            <div className="flex gap-1">
              {(["all", "seed", "auto"] as const).map((f) => (
                <Button key={f} variant={filter === f ? "default" : "outline"} size="sm" onClick={() => setFilter(f)} className="text-xs h-7">
                  {f === "all" ? "全部" : f === "seed" ? "种子" : "自动"}</Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {filtered.length === 0 ? (<div className="p-6"><EmptyState message="暂无术语数据" /></div>) : (
            <Table><TableHeader><TableRow>
              <TableHead className="w-[40%]">English</TableHead><TableHead className="w-[40%]">中文</TableHead>
              <TableHead className="w-[10%]">来源</TableHead><TableHead className="w-[10%]">操作</TableHead>
            </TableRow></TableHeader><TableBody>
              {filtered.slice(0, 100).map((t, i) => (
                <TableRow key={i}>
                  <TableCell className="font-medium text-sm">{t.en}</TableCell>
                  <TableCell className="text-sm">{t.zh}</TableCell>
                  <TableCell><Badge variant={t.source === "seed" ? "default" : "secondary"} className="text-xs">{t.source === "seed" ? "种子" : "自动"}</Badge></TableCell>
                  <TableCell><CopyButton text={`${t.en} → ${t.zh}`} size="sm" /></TableCell>
                </TableRow>
              ))}
            </TableBody></Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
