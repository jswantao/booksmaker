"use client";

import { useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ShinyButton } from "@/components/ui/shiny-button";
import { Badge } from "@/components/ui/badge";
import { OutputBox } from "@/components/shared/output-box";
import { callTranslateStream } from "@/lib/api";
import { useAppStore } from "@/stores/app-store";
import { toast } from "sonner";

export function TranslateCard() {
  const [text, setText] = useState("");
  const [bookTitle, setBookTitle] = useState("");
  const [useTm, setUseTm] = useState(true);
  const [useRag, setUseRag] = useState(true);
  const [output, setOutput] = useState("");
  const [meta, setMeta] = useState<{ fromTm?: boolean; memoryTerms?: number; tmRefs?: unknown[] }>({});
  const [streaming, setStreaming] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const { selectedTranslateKbs } = useAppStore();

  const handleTranslate = async () => {
    if (streaming) {
      abortRef.current?.abort();
      setStreaming(false);
      return;
    }
    if (!text.trim()) {
      toast.error("请输入翻译文本");
      return;
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    setOutput("");
    setMeta({});

    try {
      const result = await callTranslateStream(
        {
          text: text.trim(),
          use_tm: useTm,
          use_rag: useRag,
          kb_ids: useRag ? selectedTranslateKbs : [],
          book_title: bookTitle.trim() || undefined,
          task: "paragraph_translate",
        },
        (chunk) => setOutput((prev) => prev + chunk),
        ctrl.signal,
      );
      if (result?.success && result.translation) {
        // 用最终翻译覆盖（含后处理结果，可能与流式累计文本略有差异）
        setOutput(result.translation);
        setMeta({
          fromTm: result.from_tm,
          memoryTerms: result.memory_terms,
        });
        toast.success(result.from_tm ? "翻译记忆命中" : "翻译完成");
      } else if (result && !result.success) {
        toast.error((result as { error?: string }).error || "翻译失败");
      }
    } catch (e) {
      if (ctrl.signal.aborted) {
        toast.info("已停止翻译");
      } else {
        toast.error("网络错误: " + (e as Error).message);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const handleClear = () => {
    if (streaming) {
      abortRef.current?.abort();
      setStreaming(false);
    }
    setOutput("");
    setText("");
    setMeta({});
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg font-heading flex items-center gap-2">
          段落翻译
          {meta.fromTm && <Badge variant="secondary" className="text-xs bg-amber-100 text-amber-800">翻译记忆命中</Badge>}
          {meta.memoryTerms ? <Badge variant="outline" className="text-xs">记忆库: {meta.memoryTerms}条</Badge> : null}
          {meta.tmRefs && (meta.tmRefs as unknown[]).length > 0 && <Badge variant="outline" className="text-xs">TM参考: {(meta.tmRefs as unknown[]).length}条</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label className="text-sm font-medium">著作名</label>
          <Input placeholder="输入著作名以启用记忆库" value={bookTitle} onChange={(e) => setBookTitle(e.target.value)} className="mt-1" />
        </div>
        <div>
          <label className="text-sm font-medium">英文段落</label>
          <Textarea placeholder="请输入英文历史段落..." value={text} onChange={(e) => setText(e.target.value)} className="mt-1 min-h-[120px]" />
        </div>
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <Checkbox id="useTmT" checked={useTm} onCheckedChange={(v) => setUseTm(!!v)} />
            <label htmlFor="useTmT" className="cursor-pointer text-sm">翻译记忆 (TM)</label>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="useRagT" checked={useRag} onCheckedChange={(v) => setUseRag(!!v)} />
            <label htmlFor="useRagT" className="cursor-pointer text-sm">知识库 (RAG)</label>
          </div>
        </div>
        <div className="flex gap-3">
          <ShinyButton onClick={handleTranslate} className="flex-1">
            {streaming ? "停止" : "翻译"}
          </ShinyButton>
          <Button variant="outline" onClick={handleClear}>清空</Button>
        </div>
        {output && <OutputBox content={output} />}
      </CardContent>
    </Card>
  );
}
