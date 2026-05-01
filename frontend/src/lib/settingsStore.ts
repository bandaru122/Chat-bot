import { create } from "zustand";
import { api } from "./api";

export interface Model {
  id: string;
  name: string;
  provider: string;
}

interface SettingsState {
  selectedModel: string;
  availableModels: Model[];
  loading: boolean;
  setSelectedModel: (model: string) => void;
  loadAvailableModels: () => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  selectedModel: "gpt-4o",
  availableModels: [
    { id: "gpt-4o", name: "GPT-4o", provider: "OpenAI" },
    { id: "gemini/gemini-2.5-flash", name: "Gemini 2.5 Flash", provider: "Google" },
  ],
  loading: false,

  setSelectedModel: (model: string) => set({ selectedModel: model }),

  loadAvailableModels: async () => {
    set({ loading: true });
    try {
      const response = await api.getAvailableModels();
      set({
        availableModels: response.data,
        loading: false,
      });
    } catch (e) {
      console.error("Failed to load models:", e);
      set({ loading: false });
      // Keep fallback models
    }
  },
}));
