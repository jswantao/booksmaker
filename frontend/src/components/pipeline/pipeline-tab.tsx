"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ShinyButton } from "@/components/ui/shiny-button";
import { OutputBox } from "@/components/shared/output-box";
import { FileUploadZone } from "@/components/shared/file-upload-zone";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { usePipelineUpload, usePipelineRun, usePipelinePause, usePipelineResume, usePipelineStatus, usePipelineResult, usePipelineStitch, usePipelineKbs, usePipelineBuildKb } from "@/hooks/use-pipeline";
import { toast } from "sonner";
import { Play, Pause, RefreshCw, Eraser, Hammer } from "lucide-react";

export function PipelineTab() {
  const [filePath, setFilePath] = useState("");
  const [memoryPath, setMemoryPath] = useState("");
  const [kbIds, setKbIds] = useState<string[]>([]);
  const [pipelineId, setPipelineId] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [output, setOutput] = useState("");
  const [autoSave, setAutoSave] = useState(10);

  // Build KB section
  const [kbFile, setKbFile] = useState<File | null>(null);
  const [kbName, setKbName] = useState("");
  const [chunkSize, setChunkSize] = useState(1200);
  const [overlap, setOverlap] = useState(150);
  const [kbFilePath, setKbFilePath] = useState("");

  const upload = usePipelineUpload();
  const run = usePipelineRun();
  const pause = usePipelinePause();
  const resume = usePipelineResume();
  const stitch = usePipelineStitch();
  const buildKb = usePipelineBuildKb();
  const { data: statusData } = usePipelineStatus(pipelineId, isRunning);
  const { data: resultData } = usePipelineResult(pipelineId, isRunning);
  const { data: kbList } = usePipelineKbs();

  const handleFile = async (file: File) => {
    const fd = new FormData(); fd.append("file", file);
    try {
      const r = await upload.mutateAsync(fd);
      if (r.success) {
        setFilePath(r.file_path);
        setMemoryPath(`memory/${file.name.replace(/\.[^.]+$/, "")}_memory.json`);
        toast.success("上传成功");
      }
    } catch { toast.error("上传失败"); }
  };

  const handleRun = async () => {
    if (!filePath) { toast.error("请先上传文件"); return; }
    try {
      const r = await run.mutateAsync({ file_path: filePath, kb_ids: kbIds, memory_path: memoryPath, auto_save_interval: autoSave });
      if (r.success) {
        const pid = memoryPath.replace(/^memory[\\/]/, "").replace(/_memory\.json$/, "").replace(/[\\/]/g, "_");
        setPipelineId(pid); setIsRunning(true); toast.success("流水线已启动");
      }
    } catch { toast.error("启动失败"); }
  };

  const handlePause = async () => { if (!pipelineId) return; try { await pause.mutateAsync(pipelineId); setIsRunning(false); } catch {} };
  const handleResume = async () => { if (!pipelineId) return; try { await resume.mutateAsync(pipelineId); setIsRunning(true); } catch {} };
  const handleStitch = async () => { if (!memoryPath) return; try { const r = await stitch.mutateAsync(memoryPath); if (r.success && r.final_output) setOutput(r.final_output); toast.success("缝合完成"); } catch { toast.error("缝合失败"); } };
  const handleClear = () => { setOutput(""); setPipelineId(null); setIsRunning(false); setFilePath(""); setMemoryPath(""); };

  const handleKbFile = async (file: File) => { setKbFile(file); const fd = new FormData(); fd.append("file", file); try { const r = await upload.mutateAsync(fd); if (r.success) setKbFilePath(r.file_path); } catch {} };

  const handleBuildKb = async () => {
    if (!kbFilePath && !filePath) { toast.error("请先上传KB文件"); return; }
    if (!kbName.trim()) { toast.error("请输入KB名称"); return; }
    try {
      const r = await buildKb.mutateAsync({ file_path: kbFilePath || filePath, kb_name: kbName.trim(), chunk_size: chunkSize, overlap });
      if (r.success) toast.success(`KB已创建: ${r.chunks || 0} 个片段`);
    } catch { toast.error("KB构建失败"); }
  };

  const toggleKb = (id: string) => setKbIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);

  const done = statusData?.chunks_done || 0;
  const total = statusData?.total_chunks || 1;
  const progress = total > 0 ? Math.min((done / total) * 100, 100) : 0;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Card>
          <CardHeader><CardTitle className="text-lg font-heading">流水线配置</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div><span className="text-sm font-medium">Step 1: 上传源文件</span>
              <FileUploadZone onFile={handleFile} accept=".txt,.md,.pdf" hint="TXT / MD / PDF" className="mt-1" />
              {filePath && <p className="text-xs text-muted-foreground mt-1">✅ {filePath}</p>}</div>
            <div><span className="text-sm font-medium">Step 2: 参考知识库 (多选)</span>
              <div className="mt-1 space-y-1 max-h-[150px] overflow-auto border rounded-md p-2">
                {(kbList?.kbs || []).map((kb: { id: string; name: string; document_count: number }) => (
                  <div key={kb.id} className="flex items-center gap-2 text-sm py-0.5">
                    <Checkbox id={`kb-${kb.id}`} checked={kbIds.includes(kb.id)} onCheckedChange={() => toggleKb(kb.id)} />
                    <label htmlFor={`kb-${kb.id}`} className="cursor-pointer flex-1">{kb.name} ({kb.document_count}条)</label>
                  </div>
                ))}
                {(!kbList?.kbs || kbList.kbs.length === 0) && <p className="text-xs text-muted-foreground p-2">暂无知识库</p>}
              </div></div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div><span className="text-sm font-medium">记忆库路径</span><Input value={memoryPath} onChange={(e) => setMemoryPath(e.target.value)} className="mt-1 text-xs" /></div>
              <div><span className="text-sm font-medium">自动保存间隔</span><Input type="number" value={autoSave} onChange={(e) => setAutoSave(Number(e.target.value))} min={1} max={50} className="mt-1" /></div>
            </div>
            <div className="flex flex-col sm:flex-row gap-2">
              <ShinyButton onClick={handleRun} className="sm:w-auto w-full">{run.isPending ? "启动中..." : "开始翻译"}</ShinyButton>
              <div className="flex gap-2">
                <Button variant="outline" onClick={handlePause} className="flex-1"><Pause className="h-4 w-4 mr-1" />暂停</Button>
                <Button variant="outline" onClick={handleResume} className="flex-1"><Play className="h-4 w-4 mr-1" />恢复</Button>
                <Button variant="outline" onClick={handleStitch} className="flex-1">缝合章节</Button>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg font-heading">流水线状态</CardTitle>
            <Button variant="ghost" size="sm" onClick={handleClear}><Eraser className="h-4 w-4" /></Button>
          </CardHeader>
          <CardContent className="space-y-4">
            <div><div className="flex justify-between text-sm mb-1"><span>{done} / {total} 段</span><Badge variant={isRunning ? "default" : "secondary"}>{isRunning ? "运行中" : "空闲"}</Badge></div><Progress value={progress} /></div>
            <div className="grid grid-cols-2 gap-3 text-sm"><div><span className="text-muted-foreground">术语:</span> <b>{statusData?.terms || 0}</b></div><div><span className="text-muted-foreground">章节:</span> <b>{statusData?.completed_chapters || 0}</b></div></div>
            {output ? <OutputBox content={output} maxHeight="300px" /> : resultData?.output ? <OutputBox content={resultData.output} maxHeight="300px" /> : <EmptyState message="暂无输出" />}
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base font-heading flex items-center gap-2"><Hammer className="h-4 w-4" />从文件构建知识库</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            <div><label className="text-xs font-medium">KB 名称</label><Input value={kbName} onChange={(e) => setKbName(e.target.value)} className="mt-1 h-8 text-sm" /></div>
            <div><label className="text-xs font-medium">分块大小</label><Input type="number" value={chunkSize} onChange={(e) => setChunkSize(Number(e.target.value))} className="mt-1 h-8 text-sm" /></div>
            <div><label className="text-xs font-medium">重叠</label><Input type="number" value={overlap} onChange={(e) => setOverlap(Number(e.target.value))} className="mt-1 h-8 text-sm" /></div>
            <div className="flex items-end"><Button size="sm" onClick={handleBuildKb} disabled={buildKb.isPending}><Hammer className="h-3 w-3 mr-1" />构建 KB</Button></div>
          </div>
          <FileUploadZone onFile={handleKbFile} accept=".txt,.md" label="上传KB源文件" hint={kbFilePath ? `✅ ${kbFilePath}` : "TXT / MD"} className="py-2" />
        </CardContent>
      </Card>
    </div>
  );
}
