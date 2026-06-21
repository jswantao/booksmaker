"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useKbList, useCreateKb, useUpdateKb } from "@/hooks/use-kb";
import { toast } from "sonner";
import type { KbInfo } from "@/types/api";

interface Props { open: boolean; editId?: string; onClose: () => void; }

export function KbFormDialog({ open, editId, onClose }: Props) {
  const { data } = useKbList();
  const createKb = useCreateKb();
  const updateKb = useUpdateKb();
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [embedding, setEmbedding] = useState("");
  const [groupId, setGroupId] = useState("");

  const existing = editId ? (data?.kbs || []).find((kb: KbInfo) => kb.id === editId) : null;

  useEffect(() => {
    if (open) {
      setName(existing?.name || "");
      setDesc(existing?.description || "");
      setEmbedding(existing?.embedding_model || "");
      setGroupId(existing?.group_id || "");
    }
  }, [open, editId, existing]);

  const handleSave = async () => {
    if (!name.trim()) { toast.error("请输入名称"); return; }
    try {
      if (editId) {
        await updateKb.mutateAsync({ id: editId, body: { name: name.trim(), description: desc || null, group_id: groupId || null, embedding_model: embedding || null } });
      } else {
        await createKb.mutateAsync({ name: name.trim(), description: desc || null, group_id: groupId || null, embedding_model: embedding || null });
      }
      toast.success(editId ? "已更新" : "已创建");
      onClose();
    } catch (e) { toast.error("操作失败"); }
  };

  const groups = data?.groups || [];

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader><DialogTitle>{editId ? "编辑知识库" : "新建知识库"}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><label className="text-sm font-medium">名称</label><Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" /></div>
          <div><label className="text-sm font-medium">描述</label><Textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} className="mt-1" /></div>
          <div><label className="text-sm font-medium">Embedding 模型</label>
            <Select value={embedding} onValueChange={(v) => setEmbedding(v || "")}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="跟随全局" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">跟随全局</SelectItem>
                <SelectItem value="bge">BGE 本地</SelectItem>
                <SelectItem value="openai">OpenAI</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div><label className="text-sm font-medium">分组</label>
            <Select value={groupId} onValueChange={(v) => setGroupId(v || "")}>
              <SelectTrigger className="mt-1"><SelectValue placeholder="无分组" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="">无分组</SelectItem>
                {groups.map((g: any) => <SelectItem key={g.id} value={g.id}>{g.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={handleSave} disabled={createKb.isPending || updateKb.isPending}>{editId ? "保存" : "创建"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
