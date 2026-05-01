// Backend API client. All HTTP lives here; components/pages call `api.*`.
import type {
  ChatMessage,
  ChatResponse,
  HealthResponse,
  Note,
  Thread,
  ThreadDetail,
  User,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    if (res.status === 401) throw new Error("UNAUTHORIZED");
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  // Health
  health: () => http<HealthResponse>("/api/health"),

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
  googleLoginUrl: () => `${API_BASE}/api/auth/google/login`,

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
  sendMessage: (threadId: string, content: string, model?: string) =>
    http<ThreadDetail>(`/api/threads/${threadId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, model }),
    }),
  editMessage: (threadId: string, messageId: string, content: string, model?: string) =>
    http<ThreadDetail>(`/api/threads/${threadId}/messages/${messageId}`, {
      method: "PATCH",
      body: JSON.stringify({ content, model }),
    }),

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
};

