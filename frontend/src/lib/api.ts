// Backend API client. All HTTP lives here; components/pages call `api.*`.
import type {
  ChatMessage,
  ChatResponse,
  HealthResponse,
  Note,
  Thread,
  ThreadDetail,
  ChatMode,
  UploadedFileAsset,
  User,
} from "../types";

const CONFIGURED_API_BASE = import.meta.env.VITE_API_BASE as string | undefined;

function buildApiBaseCandidates(): string[] {
  if (CONFIGURED_API_BASE) {
    return [CONFIGURED_API_BASE];
  }

  const host = typeof window !== "undefined" ? window.location.hostname : "localhost";
  // Keep the same hostname to preserve cookie-scoped auth (localhost != 127.0.0.1).
  const sameHostCandidates = [`http://${host}:8000`, `http://${host}:8001`];
  return sameHostCandidates.filter((v, i, arr) => arr.indexOf(v) === i);
}

const API_BASE_CANDIDATES = buildApiBaseCandidates();
const REQUEST_TIMEOUT_MS = 10000;
// LLM-backed endpoints (send/edit message) can take 30-120s depending on
// model and query complexity. A 10s global timeout causes the frontend to
// abort the request, the backend still completes and saves the messages, but
// the UI shows an error. On refresh the messages reappear — confusing UX.
// Using a generous per-call timeout removes this race.
const LLM_REQUEST_TIMEOUT_MS = 120_000;

async function fetchWithTimeout(url: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timer);
  }
}

async function http<T>(path: string, init?: RequestInit, timeoutMs = REQUEST_TIMEOUT_MS): Promise<T> {
  let lastNetworkError: unknown = null;

  for (const base of API_BASE_CANDIDATES) {
    try {
      const res = await fetchWithTimeout(`${base}${path}`, {
        credentials: "include",
        headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
        ...init,
      }, timeoutMs);
      if (!res.ok) {
        if (res.status === 401) throw new Error("UNAUTHORIZED");
        const text = await res.text();
        let message = `${res.status} ${res.statusText}`;
        try {
          const body = JSON.parse(text);
          const detail = body?.detail;
          if (typeof detail === "string") message = detail;
          else if (detail && typeof detail === "object") {
            message = detail.message || detail.error || JSON.stringify(detail);
          } else if (body?.message) message = body.message;
          else if (text) message = text;
        } catch {
          if (text) message = text;
        }
        throw new Error(message);
      }
      return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const isNetworkIssue =
        message.includes("Failed to fetch") ||
        message.includes("NetworkError") ||
        message.includes("aborted") ||
        message.includes("AbortError");
      if (!isNetworkIssue) {
        throw err;
      }
      lastNetworkError = err;
    }
  }

  throw (lastNetworkError instanceof Error
    ? lastNetworkError
    : new Error("Unable to reach backend API"));
}

function parseErrorMessage(status: number, statusText: string, text: string): string {
  let message = `${status} ${statusText}`;
  try {
    const body = JSON.parse(text);
    const detail = body?.detail;
    if (typeof detail === "string") message = detail;
    else if (detail && typeof detail === "object") {
      message = detail.message || detail.error || JSON.stringify(detail);
    } else if (body?.message) message = body.message;
    else if (text) message = text;
  } catch {
    if (text) message = text;
  }
  return message;
}

export const api = {
  // Health
  health: () => http<HealthResponse>("/api/health"),

  // Models
  getAvailableModels: () =>
    http<{ data: Array<{ id: string; name: string; provider: string }> }>("/api/models"),

  // Auth
  register: (email: string, password: string, full_name?: string) =>
    http<User>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name }),
    }),
  login: (email: string, password: string) =>
    http<User>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => http<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => http<User>("/api/auth/me"),
  googleLoginUrl: () => `${API_BASE_CANDIDATES[0] ?? "http://localhost:8000"}/api/auth/google/login`,

  // Threads
  listThreads: () => http<Thread[]>("/api/threads"),
  createThread: (title?: string) =>
    http<Thread>("/api/threads", {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  getThread: (id: string) => http<ThreadDetail>(`/api/threads/${id}`),
  renameThread: (id: string, title: string) =>
    http<Thread>(`/api/threads/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  deleteThread: (id: string) =>
    http<void>(`/api/threads/${id}`, { method: "DELETE" }),
  sendMessage: (
    threadId: string,
    content: string,
    model?: string,
    mode: ChatMode = "chat",
    useRag = true
  ) =>
    http<ThreadDetail>(`/api/threads/${threadId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, model, mode, use_rag: useRag }),
    }, LLM_REQUEST_TIMEOUT_MS),
  editMessage: (
    threadId: string,
    messageId: string,
    content: string,
    model?: string,
    mode: ChatMode = "chat",
    useRag = true
  ) =>
    http<ThreadDetail>(`/api/threads/${threadId}/messages/${messageId}`, {
      method: "PATCH",
      body: JSON.stringify({ content, model, mode, use_rag: useRag }),
    }, LLM_REQUEST_TIMEOUT_MS),
  getSuggestions: (threadId: string) =>
    http<string[]>(`/api/threads/${threadId}/suggestions`),
  uploadFiles: async (files: File[]) => {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
    }

    let lastNetworkError: unknown = null;

    for (const base of API_BASE_CANDIDATES) {
      try {
        const res = await fetchWithTimeout(`${base}/api/files/upload`, {
          method: "POST",
          credentials: "include",
          body: form,
        });
        if (!res.ok) {
          if (res.status === 401) throw new Error("UNAUTHORIZED");
          const text = await res.text();
          throw new Error(parseErrorMessage(res.status, res.statusText, text));
        }
        const body = (await res.json()) as { files: UploadedFileAsset[] };
        return body.files;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        const isNetworkIssue =
          message.includes("Failed to fetch") ||
          message.includes("NetworkError") ||
          message.includes("aborted") ||
          message.includes("AbortError");
        if (!isNetworkIssue) {
          throw err;
        }
        lastNetworkError = err;
      }
    }

    throw (lastNetworkError instanceof Error
      ? lastNetworkError
      : new Error("Unable to reach backend API"));
  },

  // Notes
  listNotes: () => http<Note[]>("/api/notes"),
  createNote: (title: string, content: string) =>
    http<Note>("/api/notes", { method: "POST", body: JSON.stringify({ title, content }) }),
  deleteNote: (id: number) => http<void>(`/api/notes/${id}`, { method: "DELETE" }),
  summarize: (id: number) =>
    http<{ note_id: number; summary: string }>("/api/summarize", {
      method: "POST",
      body: JSON.stringify({ note_id: id }),
    }),

  // Simple chat (no thread, no auth — P1 fallback)
  chat: (messages: ChatMessage[]) =>
    http<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify({ messages }) }),

  // LangChain ReAct agent (autonomous tool selection over weather/crypto/news)
  agentChat: (query: string) =>
    http<{
      ok: boolean;
      answer: string;
      steps: Array<{ tool: string; tool_input: unknown; log: string; observation: string }>;
    }>("/api/agent/chat", { method: "POST", body: JSON.stringify({ query }) }),

  // Stream agent thinking events as SSE. Calls onEvent for every parsed event.
  agentChatStream: async (
    query: string,
    onEvent: (event: { type: string; data: Record<string, unknown> }) => void,
    signal?: AbortSignal
  ): Promise<void> => {
    let lastNetworkError: unknown = null;
    for (const base of API_BASE_CANDIDATES) {
      try {
        const url = `${base}/api/agent/chat/stream?query=${encodeURIComponent(query)}`;
        const res = await fetch(url, {
          method: "GET",
          credentials: "include",
          headers: { Accept: "text/event-stream" },
          signal,
        });
        if (!res.ok) {
          if (res.status === 401) throw new Error("UNAUTHORIZED");
          const text = await res.text();
          throw new Error(`${res.status} ${res.statusText}: ${text}`);
        }
        const reader = res.body?.getReader();
        if (!reader) throw new Error("No response body for SSE stream");
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // Split on SSE event boundary (blank line).
          let idx;
          while ((idx = buffer.indexOf("\n\n")) !== -1) {
            const raw = buffer.slice(0, idx);
            buffer = buffer.slice(idx + 2);
            // Parse `data:` lines; ignore comments (`:` prefix) and `event:`.
            const dataLines = raw
              .split("\n")
              .filter((l) => l.startsWith("data:"))
              .map((l) => l.slice(5).trimStart());
            if (dataLines.length === 0) continue;
            const payload = dataLines.join("\n");
            if (!payload || payload === "{}") continue;
            try {
              const parsed = JSON.parse(payload) as {
                type: string;
                data: Record<string, unknown>;
              };
              onEvent(parsed);
            } catch {
              // Ignore malformed events.
            }
          }
        }
        return;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        const isNetworkIssue =
          message.includes("Failed to fetch") ||
          message.includes("NetworkError") ||
          message.includes("aborted") ||
          message.includes("AbortError");
        if (!isNetworkIssue) throw err;
        lastNetworkError = err;
      }
    }
    throw lastNetworkError instanceof Error
      ? lastNetworkError
      : new Error("Unable to reach backend API");
  },
};

