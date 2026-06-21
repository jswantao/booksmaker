"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { useKbList, useDeleteKb, useDeleteGroup } from "@/hooks/use-kb";
import type { KbInfo, KbGroup } from "@/types/api";
import { Plus, Folder, Book, Upload, Pencil, Trash2, RefreshCw, ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { KbFormDialog } from "./kb-form-dialog";
import { GroupFormDialog } from "./group-form-dialog";
import { useState } from "react";

export function KbManagerTab() {
  const { data, refetch } = useKbList();
  const deleteKb = useDeleteKb();
  const deleteGroup = useDeleteGroup();
  const [kbDialog, setKbDialog] = useState<{ open: boolean; editId?: string }>({ open: false });
  const [groupDialog, setGroupDialog] = useState<{ open: boolean; editId?: string }>({ open: false });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const kbs = data?.kbs || [];
  const groups = data?.groups || [];
  const ungrouped = kbs.filter((kb: KbInfo) => !kb.group_id);

  const handleDeleteKb = async (id: string) => {
    if (!confirm("确定删除此知识库？向量数据将一并删除！")) return;
    try { await deleteKb.mutateAsync(id); toast.success("已删除"); } catch {}
  };

  const handleDeleteGroup = async (id: string) => {
    if (!confirm("确定删除此分组？")) return;
    try { await deleteGroup.mutateAsync(id); toast.success("已删除"); } catch {}
  };

  const handleUpload = (kbId: string) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".txt,.md";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      try {
        const { uploadToKb } = await import("@/lib/api");
        const r = await uploadToKb(kbId, fd);
        if (r.success) { toast.success(r.message); refetch(); }
      } catch (e) { toast.error("上传失败"); }
    };
    input.click();
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Button size="sm" onClick={() => setKbDialog({ open: true })}><Plus className="h-4 w-4 mr-1" />新建知识库</Button>
        <Button size="sm" variant="outline" onClick={() => setGroupDialog({ open: true })}><Plus className="h-4 w-4 mr-1" />新建分组</Button>
        <Button size="sm" variant="ghost" onClick={() => refetch()}><RefreshCw className="h-4 w-4" /></Button>
      </div>

      <Card>
        <CardContent className="p-0">
          {kbs.length === 0 ? (
            <div className="p-6"><EmptyState message="暂无知识库，点击上方按钮创建" /></div>
          ) : (
            <div>
              {groups.map((g: KbGroup) => {
                const groupKbs = kbs.filter((kb: KbInfo) => kb.group_id === g.id);
                const isExpanded = expanded[g.id] !== false;
                return (
                  <div key={g.id}>
                    <div
                      className="flex items-center gap-2 px-4 py-2 cursor-pointer hover:bg-muted/50 border-b border-border"
                      onClick={() => setExpanded((e) => ({ ...e, [g.id]: !isExpanded }))}
                    >
                      {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      <Folder className="h-4 w-4 text-amber-600" />
                      <span className="font-medium text-sm flex-1">{g.name}</span>
                      <Badge variant="secondary" className="text-xs">{groupKbs.length}</Badge>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setGroupDialog({ open: true, editId: g.id }); }}>
                        <Pencil className="h-3 w-3" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); handleDeleteGroup(g.id); }}>
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                    {isExpanded && groupKbs.map((kb: KbInfo) => (
                      <KbItemRow key={kb.id} kb={kb} onEdit={() => setKbDialog({ open: true, editId: kb.id })} onDelete={() => handleDeleteKb(kb.id)} onUpload={() => handleUpload(kb.id)} />
                    ))}
                  </div>
                );
              })}
              {ungrouped.length > 0 && (
                <div>
                  <div className="px-4 py-2 text-xs text-muted-foreground border-b border-border">未分组</div>
                  {ungrouped.map((kb: KbInfo) => (
                    <KbItemRow key={kb.id} kb={kb} onEdit={() => setKbDialog({ open: true, editId: kb.id })} onDelete={() => handleDeleteKb(kb.id)} onUpload={() => handleUpload(kb.id)} />
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <KbFormDialog open={kbDialog.open} editId={kbDialog.editId} onClose={() => { setKbDialog({ open: false }); refetch(); }} />
      <GroupFormDialog open={groupDialog.open} editId={groupDialog.editId} onClose={() => { setGroupDialog({ open: false }); refetch(); }} />
    </div>
  );
}

function KbItemRow({ kb, onEdit, onDelete, onUpload }: { kb: KbInfo; onEdit: () => void; onDelete: () => void; onUpload: () => void }) {
  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-border hover:bg-muted/30 text-sm">
      <Book className="h-4 w-4 text-muted-foreground" />
      <span className="flex-1 font-medium">{kb.name}</span>
      <Badge variant="outline" className="text-xs">{kb.document_count} 条</Badge>
      <span className="text-xs text-muted-foreground">{kb.embedding_model || "默认"}</span>
      <Button variant="ghost" size="sm" onClick={onUpload}><Upload className="h-3 w-3" /></Button>
      <Button variant="ghost" size="sm" onClick={onEdit}><Pencil className="h-3 w-3" /></Button>
      <Button variant="ghost" size="sm" onClick={onDelete}><Trash2 className="h-3 w-3" /></Button>
    </div>
  );
}
