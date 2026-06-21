"use client";

import { Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { Header } from "@/components/layout/header";
import { MainTabs } from "@/components/layout/main-tabs";
import { WorkspaceTab } from "@/components/workspace/workspace-tab";
import { Loader2 } from "lucide-react";

// 动态导入：构建期不要求文件存在，运行时按需加载
const KbManagerTab = dynamic(
  () => import("@/components/kb-manager/kb-manager-tab").then((m) => ({ default: m.KbManagerTab })),
  { loading: () => <TabFallback name="知识库管理" /> }
);

const PipelineTab = dynamic(
  () => import("@/components/pipeline/pipeline-tab").then((m) => ({ default: m.PipelineTab })),
  { loading: () => <TabFallback name="翻译流水线" /> }
);

const MemoryTab = dynamic(
  () => import("@/components/memory/memory-tab").then((m) => ({ default: m.MemoryTab })),
  { loading: () => <TabFallback name="记忆库" /> }
);

const TrainingTab = dynamic(
  () => import("@/components/training/training-tab").then((m) => ({ default: m.TrainingTab })),
  { loading: () => <TabFallback name="模型训练" /> }
);

const VALID_TABS = ["workspace", "kbmanager", "pipeline", "memory", "training"] as const;
type Tab = (typeof VALID_TABS)[number];

function TabFallback({ name }: { name: string }) {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground">
      <Loader2 className="animate-spin mr-2" size={18} />
      {name} — 加载中...
    </div>
  );
}

function TabContent({ tab }: { tab: Tab }) {
  switch (tab) {
    case "workspace":
      return <WorkspaceTab />;
    case "kbmanager":
      return <KbManagerTab />;
    case "pipeline":
      return <PipelineTab />;
    case "memory":
      return <MemoryTab />;
    case "training":
      return <TrainingTab />;
    default:
      return <WorkspaceTab />;
  }
}

function PageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const tab = (searchParams.get("tab") || "workspace") as Tab;

  const setTab = (t: string) => {
    router.push(`/?tab=${t}`);
  };

  return (
    <div className="container mx-auto max-w-[1560px] px-4 sm:px-6 py-6">
      <Header />
      <MainTabs activeTab={tab} onTabChange={setTab} />
      <div className="mt-7">
        <TabContent tab={tab} />
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen">
          <Loader2 className="animate-spin" size={24} />
        </div>
      }
    >
      <PageInner />
    </Suspense>
  );
}
