// Zustand: client-only UI state

import { create } from "zustand";

interface AppState {
  // Active tab
  activeTab: "workspace" | "kbmanager" | "pipeline" | "memory";
  setActiveTab: (tab: AppState["activeTab"]) => void;

  // Config panel
  isConfigExpanded: boolean;
  toggleConfig: () => void;
  setConfigExpanded: (v: boolean) => void;

  // KB selections per panel
  selectedTranslateKbs: string[];
  selectedEpubKbs: string[];
  setSelectedTranslateKbs: (ids: string[]) => void;
  setSelectedEpubKbs: (ids: string[]) => void;

  // KB picker modal
  isKbPickerOpen: boolean;
  kbPickerPanel: "translate" | "epub" | null;
  openKbPicker: (panel: "translate" | "epub") => void;
  closeKbPicker: () => void;

  // Loading locks (by action key)
  loadingActions: Record<string, boolean>;
  setLoading: (action: string, loading: boolean) => void;
  isLoading: (action: string) => boolean;
}

export const useAppStore = create<AppState>((set, get) => ({
  activeTab: "workspace",
  setActiveTab: (tab) => set({ activeTab: tab }),

  isConfigExpanded: true,
  toggleConfig: () => set((s) => ({ isConfigExpanded: !s.isConfigExpanded })),
  setConfigExpanded: (v) => set({ isConfigExpanded: v }),

  selectedTranslateKbs: [],
  selectedEpubKbs: [],
  setSelectedTranslateKbs: (ids) => set({ selectedTranslateKbs: ids }),
  setSelectedEpubKbs: (ids) => set({ selectedEpubKbs: ids }),

  isKbPickerOpen: false,
  kbPickerPanel: null,
  openKbPicker: (panel) => set({ isKbPickerOpen: true, kbPickerPanel: panel }),
  closeKbPicker: () => set({ isKbPickerOpen: false, kbPickerPanel: null }),

  loadingActions: {},
  setLoading: (action, loading) =>
    set((s) => ({
      loadingActions: { ...s.loadingActions, [action]: loading },
    })),
  isLoading: (action) => !!get().loadingActions[action],
}));
