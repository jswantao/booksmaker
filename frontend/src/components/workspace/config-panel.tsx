"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ShinyButton } from "@/components/ui/shiny-button";
import { Badge } from "@/components/ui/badge";
import { useConfig, useSaveConfig, useLlmStatus, useEmbeddingStatus, useModelScopeSearch } from "@/hooks/use-config";
import { useAppStore } from "@/stores/app-store";
import { ChevronUp, ChevronDown, Loader2 } from "lucide-react";
import { toast } from "sonner";
import type { ConfigRequest, ModelScopeModel } from "@/types/api";

const DEFAULT_CONFIG: ConfigRequest = {
  api_key: "", base_url: "https://api.openai.com/v1", model_name: "gpt-4o-mini",
  embedding_model: "text-embedding-3-small", embedding_provider: "openai",
  bge_model_id: "BAAI/bge-base-zh-v1.5", llm_provider: "openai",
  local_translate_model: "Qwen/Qwen2-7B-Instruct", local_epub_model: "",
  download_source: "huggingface", modelscope_cache_dir: "",
};

export function ConfigPanel() {
  const { data: config } = useConfig();
  const saveConfig = useSaveConfig();
  const { data: llmStatus } = useLlmStatus();
  const { data: embedStatus } = useEmbeddingStatus();
  const { isConfigExpanded, toggleConfig } = useAppStore();
  const [form, setForm] = useState<ConfigRequest>(DEFAULT_CONFIG);
  const [searchQ, setSearchQ] = useState("");
  const [showModelSearch, setShowModelSearch] = useState(false);
  const { data: modelData, refetch: searchModels } = useModelScopeSearch(searchQ, 7);

  const isConfigured = config?.is_configured;
  const isLocal = form.llm_provider === "local";
  const transStatus = (llmStatus?.status as Record<string, { status: string; load_error?: string }>)?.translate;
  const bgeLoaded = embedStatus?.loaded;

  useEffect(() => {
    if (config) setForm((prev) => ({ ...prev, ...config, api_key: config.api_key === "***" ? "" : (config.api_key || "") }));
  }, [config]);

  const update = (key: keyof ConfigRequest, value: string | null) => setForm((f) => ({ ...f, [key]: value || "" }));

  const handleSave = async () => {
    if (!isLocal && !form.api_key) { toast.error("远程模式请填写 API Key"); return; }
    try {
      const r = await saveConfig.mutateAsync(form);
      if (r.success) toast.success("配置已保存");
    } catch (e) { toast.error("保存失败: " + (e as Error).message); }
  };

  const handleReset = () => { setForm({ ...DEFAULT_CONFIG }); toast.success("已重置表单"); };

  const handleModelSearch = async () => {
    setShowModelSearch(true);
    await searchModels();
  };

  const selectModel = (id: string) => {
    update("local_translate_model", id);
    setShowModelSearch(false);
    toast.success(`已选择: ${id}`);
  };

  const statusText = isConfigured ? "已配置" : "未配置";
  const configSummary = `⚡ ${isLocal ? `本地 (${form.local_translate_model})` : `OpenAI (${form.model_name})`} | ${form.embedding_provider === "bge" ? "BGE 向量" : "OpenAI 向量"}`;

  return (
    <Card>
      <CardHeader className="cursor-pointer select-none flex flex-row items-center justify-between py-3" onClick={toggleConfig}>
        <div className="flex items-center gap-2 flex-wrap">
          <CardTitle className="text-base font-heading">API 配置</CardTitle>
          <Badge variant={isConfigured ? "default" : "secondary"}>{statusText}</Badge>
          <span className="text-xs text-muted-foreground hidden sm:inline">{configSummary}</span>
        </div>
        <Button variant="ghost" size="sm" type="button">{isConfigExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</Button>
      </CardHeader>
      {isConfigExpanded && (
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium">LLM 提供者</label>
              <Select value={form.llm_provider} onValueChange={(v) => update("llm_provider", v)}>
                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai">OpenAI API</SelectItem>
                  <SelectItem value="local">本地模型</SelectItem>
                </SelectContent>
              </Select>
              {isLocal && transStatus && (
                <p className="text-xs mt-1 text-muted-foreground">
                  {transStatus.status === "ready" ? "✅ 本地 LLM 就绪" :
                   transStatus.status === "loading" || transStatus.status === "downloading" ? "⏳ 正在加载本地模型..." :
                   transStatus.status === "error" ? `❌ ${transStatus.load_error || "加载失败"}` :
                   "📦 尚未加载"}
                </p>
              )}
            </div>
            {!isLocal && (
              <div>
                <label className="text-sm font-medium">API Key</label>
                <Input type="password" placeholder="sk-..." className="mt-1"
                  value={form.api_key} onChange={(e) => update("api_key", e.target.value)} />
              </div>
            )}
          </div>
          {!isLocal && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium">API 地址</label>
                <Input className="mt-1" placeholder="https://api.openai.com/v1"
                  value={form.base_url} onChange={(e) => update("base_url", e.target.value)} />
              </div>
              <div>
                <label className="text-sm font-medium">模型名称</label>
                <Input className="mt-1" placeholder="gpt-4o-mini"
                  value={form.model_name} onChange={(e) => update("model_name", e.target.value)} />
              </div>
            </div>
          )}
          {isLocal && (
            <div className="space-y-3">
              <div>
                <label className="text-sm font-medium">本地翻译模型
                  <Button variant="link" size="sm" className="text-xs h-auto p-0 ml-2" onClick={handleModelSearch}>搜索魔搭模型</Button>
                </label>
                <Input className="mt-1" placeholder="Qwen/Qwen2-7B-Instruct"
                  value={form.local_translate_model} onChange={(e) => update("local_translate_model", e.target.value)} />
              </div>
              {showModelSearch && modelData?.models && (
                <div className="border rounded-md max-h-[200px] overflow-auto bg-card">
                  {modelData.models.map((m: ModelScopeModel) => (
                    <div key={m.id} className="px-3 py-2 cursor-pointer hover:bg-muted border-b flex justify-between text-sm"
                      onClick={() => selectModel(m.id)}>
                      <span><b>{m.name}</b> <span className="text-muted-foreground text-xs">{m.family}</span></span>
                      <span className="flex gap-2 items-center">
                        <Badge variant="outline" className="text-xs">{m.params}</Badge>
                        {m.on_modelscope ? <Badge className="text-xs bg-green-100 text-green-700">魔搭</Badge> : <Badge variant="secondary" className="text-xs">HF</Badge>}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label className="text-sm font-medium">下载源</label>
                  <Select value={form.download_source} onValueChange={(v) => update("download_source", v)}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="huggingface">HuggingFace</SelectItem>
                      <SelectItem value="modelscope">ModelScope</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {form.download_source === "modelscope" && (
                  <div><label className="text-sm font-medium">缓存目录</label>
                    <Input className="mt-1" placeholder="默认"
                      value={form.modelscope_cache_dir || ""} onChange={(e) => update("modelscope_cache_dir", e.target.value)} /></div>
                )}
              </div>
            </div>
          )}
          <div>
            <label className="text-sm font-medium">Embedding 提供者</label>
            <Select value={form.embedding_provider} onValueChange={(v) => update("embedding_provider", v)}>
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="openai">OpenAI API</SelectItem>
                <SelectItem value="bge">BGE 本地模型</SelectItem>
              </SelectContent>
            </Select>
            {form.embedding_provider === "bge" && (
              <p className="text-xs mt-1 text-muted-foreground">
                {bgeLoaded ? "✅ BGE 就绪" : embedStatus?.error ? `❌ ${embedStatus.error}` : "📦 首次使用将自动加载(~102MB)"}
              </p>
            )}
          </div>
          <div className="flex justify-end gap-3 pt-2 border-t border-border">
            <Button variant="outline" type="button" onClick={handleReset}>重置配置</Button>
            <ShinyButton onClick={handleSave}>{saveConfig.isPending ? "保存中..." : "保存并测试"}</ShinyButton>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
