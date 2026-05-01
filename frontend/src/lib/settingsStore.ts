import { create } from "zustand";

export const AVAILABLE_MODELS = [
  { id: "gpt-4o", label: "GPT-4o", provider: "OpenAI" },
  { id: "gemini/gemini-2.5-flash", label: "Gemini 2.5 Flash", provider: "Google" },
] as const;

interface SettingsState {
  selectedModel: string;
  setSelectedModel: (model: string) => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  selectedModel: "gpt-4o",
  setSelectedModel: (model: string) => set({ selectedModel: model }),
}));
