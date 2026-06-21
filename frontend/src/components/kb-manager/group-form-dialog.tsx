"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { useKbList, useCreateGroup, useUpdateGroup } from "@/hooks/use-kb";
import { toast } from "sonner";
import type { KbGroup } from "@/types/api";

interface Props { open: boolean; editId?: string; onClose: () => void; }

export function GroupFormDialog({ open, editId, onClose }: Props) {
  const { data } = useKbList();
  const createGroup = useCreateGroup();
  const updateGroup = useUpdateGroup();
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");

  const existing = editId ? (data?.groups || []).find((g: KbGroup) => g.id === editId) : null;

  useEffect(() => {
    if (open) { setName(existing?.name || ""); setDesc(existing?.description || ""); }
  }, [open, editId, existing]);

  const handleSave = async () => {
    if (!name.trim()) { toast.error("请输入名称"); return; }
    try {
      if (editId) await updateGroup.mutateAsync({ id: editId, body: { name: name.trim(), description: desc || null } });
      else await createGroup.mutateAsync({ name: name.trim(), description: desc || null });
      toast.success(editId ? "已更新" : "已创建"); onClose();
    } catch (e) { toast.error("操作失败"); }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader><DialogTitle>{editId ? "编辑分组" : "新建分组"}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><label className="text-sm font-medium">名称</label><Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1" /></div>
          <div><label className="text-sm font-medium">描述</label><Textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} className="mt-1" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={handleSave} disabled={createGroup.isPending || updateGroup.isPending}>{editId ? "保存" : "创建"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
