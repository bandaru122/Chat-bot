import { create } from "zustand";
import type { ChatMode, MessageRow, Thread } from "../types";
import { api } from "./api";
import { useSettingsStore } from "./settingsStore";

// Persisted across reloads so the user lands back on the thread they had open.
const ACTIVE_THREAD_KEY = "chat.activeThreadId";

// Guard against out-of-order async updates (thread loads / selections)
// that can transiently wipe messages in dev StrictMode or slow networks.
let loadThreadsInFlight: Promise<void> | null = null;
let selectThreadRequestSeq = 0;

function readPersistedActiveId(): string | null {
  try {
    return typeof window !== "undefined"
      ? window.localStorage.getItem(ACTIVE_THREAD_KEY)
      : null;
  } catch {
    return null;
  }
}

function writePersistedActiveId(id: string | null): void {
  try {
    if (typeof window === "undefined") return;
    if (id) window.localStorage.setItem(ACTIVE_THREAD_KEY, id);
    else window.localStorage.removeItem(ACTIVE_THREAD_KEY);
  } catch {
    /* ignore quota / private-mode errors */
  }
}

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
  sendMessage: (
    content: string,
    attachments?: File[],
    mode?: ChatMode,
    modelOverride?: string,
    useRag?: boolean
  ) => Promise<void>;
  editMessage: (messageId: string, newContent: string) => Promise<void>;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  threads: [],
  activeId: null,
  messages: [],
  loading: false,

  loadThreads: async () => {
    if (loadThreadsInFlight) {
      await loadThreadsInFlight;
      return;
    }

    loadThreadsInFlight = (async () => {
      const threads = await api.listThreads();
      set({ threads });

      // Auto-select a thread on first load / page refresh so the user is
      // never dropped onto an empty Hero state when they have existing chats.
      const { activeId } = get();
      if (activeId && threads.some((t) => t.id === activeId)) return;

      const persisted = readPersistedActiveId();
      const restoreId =
        (persisted && threads.some((t) => t.id === persisted) ? persisted : null) ??
        threads[0]?.id ??
        null;
      if (restoreId) {
        await get().selectThread(restoreId);
      }
    })();

    try {
      await loadThreadsInFlight;
    } finally {
      loadThreadsInFlight = null;
    }
  },

  selectThread: async (id: string) => {
    const reqId = ++selectThreadRequestSeq;
    set({ activeId: id, loading: true });
    writePersistedActiveId(id);
    try {
      const detail = await api.getThread(id);
      // Ignore stale responses from older select-thread calls.
      if (reqId !== selectThreadRequestSeq) return;
      set((s) => {
        if (s.activeId !== id) return { loading: false };
        return { messages: detail.messages, loading: false };
      });
    } catch {
      // Keep existing messages on transient fetch errors; they can be reloaded.
      if (reqId !== selectThreadRequestSeq) return;
      set({ loading: false });
    }
  },

  createThread: async () => {
    const t = await api.createThread();
    set((s) => ({
      threads: [t, ...s.threads],
      activeId: t.id,
      messages: [],
    }));
    writePersistedActiveId(t.id);
    return t.id;
  },

  deleteThread: async (id: string) => {
    await api.deleteThread(id);
    set((s) => {
      const threads = s.threads.filter((t) => t.id !== id);
      const activeId = s.activeId === id ? threads[0]?.id ?? null : s.activeId;
      if (s.activeId === id) writePersistedActiveId(activeId);
      return { threads, activeId, messages: s.activeId === id ? [] : s.messages };
    });
  },

  renameThread: async (id: string, title: string) => {
    const updated = await api.renameThread(id, title);
    set((s) => ({
      threads: s.threads.map((t) => (t.id === id ? updated : t)),
    }));
  },

  sendMessage: async (
    content: string,
    attachments: File[] = [],
    mode: ChatMode = "chat",
    modelOverride?: string,
    useRag = true
  ) => {
    let { activeId } = get();
    if (!activeId) {
      activeId = await get().createThread();
    }
    const targetThreadId = activeId;

    let composedContent = content;
    if (attachments.length > 0) {
      const uploaded = await api.uploadFiles(attachments);
      const lines = uploaded.map(
        (f) =>
          `- [${f.filename}](${f.url}) (${f.content_type}, ${Math.max(1, Math.round(f.size / 1024))}KB)`
      );
      composedContent = `${content}\n\nAttached files:\n${lines.join("\n")}`;
    }

    // Optimistic: add user msg
    const userMsg: MessageRow = {
      id: crypto.randomUUID(),
      role: "user",
      content: composedContent,
      created_at: new Date().toISOString(),
    };
    set((s) => ({ messages: [...s.messages, userMsg], loading: true }));

    try {
      const model = modelOverride || useSettingsStore.getState().selectedModel;
      const detail = await api.sendMessage(targetThreadId, composedContent, model, mode, useRag);
      // Update thread metadata always; only replace messages when still viewing
      // the same thread to avoid out-of-order UI clobbering.
      set((s) => ({
        messages: s.activeId === detail.id ? detail.messages : s.messages,
        loading: false,
        // Update thread title (auto-generated on first message)
        threads: s.threads.map((t) =>
          t.id === detail.id ? { ...t, title: detail.title, updated_at: detail.updated_at } : t
        ),
      }));
    } catch (e) {
      // Roll back the optimistic message: it was never persisted server-side,
      // so leaving it in the UI would let the user "edit" a phantom message
      // by id, producing a 404 "Message not found" on the PATCH endpoint.
      set((s) => ({
        messages: s.activeId === targetThreadId ? s.messages.filter((m) => m.id !== userMsg.id) : s.messages,
        loading: false,
      }));
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

  reset: () => {
    writePersistedActiveId(null);
    set({ threads: [], activeId: null, messages: [], loading: false });
  },
}));
