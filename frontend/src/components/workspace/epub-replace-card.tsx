"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ShinyButton } from "@/components/ui/shiny-button";
import { OutputBox } from "@/components/shared/output-box";
import { useEpubReplace } from "@/hooks/use-translate";
import { toast } from "sonner";

const EXAMPLE_EPUB = `<html xmlns="http://www.w3.org/1999/xhtml">
<body>
  <p>The Treaty of Versailles was signed in 1919.</p>
</body>
</html>`;

export function EpubReplaceCard() {
  const [translation, setTranslation] = useState("");
  const [epubCode, setEpubCode] = useState("");
  const [output, setOutput] = useState("");
  const epubReplace = useEpubReplace();

  const handleReplace = async () => {
    if (!translation.trim() || !epubCode.trim()) {
      toast.error("请填写译文和 EPUB 代码");
      return;
    }
    try {
      const result = await epubReplace.mutateAsync({
        translation: translation.trim(),
        epub_code: epubCode.trim(),
      });
      if (result.success && result.epub_code) {
        setOutput(result.epub_code);
        toast.success("替换完成");
      } else {
        toast.error(result.error || "替换失败");
      }
    } catch (e) {
      toast.error("网络错误: " + (e as Error).message);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg font-heading">EPUB 替换</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium">新译文</span>
            <Button variant="link" size="sm" onClick={() => setTranslation("示例译文内容")} className="text-xs h-auto p-0">
              加载示例
            </Button>
          </div>
          <Textarea
            placeholder="输入新的中文译文..."
            value={translation}
            onChange={(e) => setTranslation(e.target.value)}
            className="min-h-[80px]"
          />
        </div>
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium">EPUB 代码（含 HTML 标签）</span>
            <Button variant="link" size="sm" onClick={() => setEpubCode(EXAMPLE_EPUB)} className="text-xs h-auto p-0">
              加载示例
            </Button>
          </div>
          <Textarea
            placeholder="输入 EPUB XHTML 代码..."
            value={epubCode}
            onChange={(e) => setEpubCode(e.target.value)}
            className="min-h-[120px] font-mono text-xs"
          />
        </div>
        <div className="flex gap-3">
          <ShinyButton onClick={handleReplace} className="flex-1">
            {epubReplace.isPending ? "替换中..." : "替换内容"}
          </ShinyButton>
          <Button variant="outline" onClick={() => { setOutput(""); }}>
            清空
          </Button>
        </div>
        {output && <OutputBox content={output} />}
      </CardContent>
    </Card>
  );
}
