import { create } from "zustand";
import type { MessageRow, Thread } from "../types";
import { api } from "./api";
import { useSettingsStore } from "./settingsStore";

interface ChatState {
  threads: Thread[];
  activeId: string | null;
  messages: MessageRow[];
  loading: boolean;

  loadThreads: () => Promise<void>;
  selectThread: (id: string) => Promise<void>;
  createThread: () => Promise<string>;
  deleteThread: (id: string) => Promise<void>;
  renameThread: (id: string, title: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  editMessage: (messageId: string, newContent: string) => Promise<void>;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  threads: [],
  activeId: null,
  messages: [],
  loading: false,

  loadThreads: async () => {
    const threads = await api.listThreads();
    set({ threads });
  },

  selectThread: async (id: string) => {
    set({ activeId: id, loading: true });
    try {
      const detail = await api.getThread(id);
      set({ messages: detail.messages, loading: false });
    } catch {
      set({ messages: [], loading: false });
    }
  },

  createThread: async () => {
    const t = await api.createThread();
    set((s) => ({
      threads: [t, ...s.threads],
      activeId: t.id,
      messages: [],
    }));
    return t.id;
  },

  deleteThread: async (id: string) => {
    await api.deleteThread(id);
    set((s) => {
      const threads = s.threads.filter((t) => t.id !== id);
      const activeId = s.activeId === id ? threads[0]?.id ?? null : s.activeId;
      return { threads, activeId, messages: s.activeId === id ? [] : s.messages };
    });
  },

  renameThread: async (id: string, title: string) => {
    const updated = await api.renameThread(id, title);
    set((s) => ({
      threads: s.threads.map((t) => (t.id === id ? updated : t)),
    }));
  },

  sendMessage: async (content: string) => {
    let { activeId } = get();
    if (!activeId) {
      activeId = await get().createThread();
    }
    // Optimistic: add user msg
    const userMsg: MessageRow = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    set((s) => ({ messages: [...s.messages, userMsg], loading: true }));

    try {
      const model = useSettingsStore.getState().selectedModel;
      const detail = await api.sendMessage(activeId!, content, model);
      // Update messages from server (has assistant response + correct IDs)
      set((s) => ({
        messages: detail.messages,
        loading: false,
        // Update thread title (auto-generated on first message)
        threads: s.threads.map((t) =>
          t.id === detail.id ? { ...t, title: detail.title, updated_at: detail.updated_at } : t
        ),
      }));
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  editMessage: async (messageId: string, newContent: string) => {
    const { activeId } = get();
    if (!activeId) return;

    set({ loading: true });
    try {
      const model = useSettingsStore.getState().selectedModel;
      const detail = await api.editMessage(activeId, messageId, newContent, model);
      set((s) => ({
        messages: detail.messages,
        loading: false,
        threads: s.threads.map((t) =>
          t.id === detail.id ? { ...t, updated_at: detail.updated_at } : t
        ),
      }));
    } catch (e) {
      set({ loading: false });
      throw e;
    }
  },

  reset: () => set({ threads: [], activeId: null, messages: [], loading: false }),
}));
