"use client";

import { ConfigPanel } from "./config-panel";
import { TranslateCard } from "./translate-card";
import { EpubReplaceCard } from "./epub-replace-card";
import { TmManager } from "./tm-manager";
import { TerminologySection } from "./terminology-section";

export function WorkspaceTab() {
  return (
    <div className="space-y-6">
      <ConfigPanel />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="space-y-6">
          <TranslateCard />
          <TmManager />
        </div>
        <div className="space-y-6">
          <EpubReplaceCard />
          <TerminologySection />
        </div>
      </div>
    </div>
  );
}
