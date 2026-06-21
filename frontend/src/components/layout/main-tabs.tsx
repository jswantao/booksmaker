"use client";

import { BookOpen, Library, Play, Database, Brain } from "lucide-react";

const TABS = [
  { key: "workspace", label: "翻译工作台", icon: BookOpen },
  { key: "kbmanager", label: "知识库管理", icon: Library },
  { key: "pipeline", label: "翻译流水线", icon: Play },
  { key: "memory", label: "记忆库", icon: Database },
  { key: "training", label: "模型训练", icon: Brain },
] as const;

interface MainTabsProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

export function MainTabs({ activeTab, onTabChange }: MainTabsProps) {
  return (
    <div
      className="inline-flex rounded-xl border border-border bg-card overflow-hidden"
      role="tablist"
      aria-label="主功能标签"
    >
      {TABS.map(({ key, label, icon: Icon }) => {
        const isActive = activeTab === key;
        return (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={isActive}
            data-tab={key}
            onClick={() => onTabChange(key)}
            className={`
              flex-1 px-4 sm:px-5 py-3 border-none cursor-pointer
              font-medium text-sm sm:text-base font-sans
              transition-all duration-200
              flex items-center gap-2
              ${
                isActive
                  ? "bg-primary/8 text-primary shadow-[inset_0_-2px_0_0_var(--color-primary)]"
                  : "bg-transparent text-muted-foreground hover:bg-muted/50"
              }
            `}
          >
            <Icon className="h-4 w-4" />
            <span className="hidden sm:inline">{label}</span>
          </button>
        );
      })}
    </div>
  );
}
