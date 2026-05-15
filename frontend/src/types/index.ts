// Shared TypeScript types for the frontend.

export interface Note {
  id: number;
  title: string;
  content: string;
  summary: string | null;
  owner_email: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  model: string;
  content: string;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface HealthResponse {
  status: string;
  app: string;
  environment: string;
  llm_model: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
}

export interface MessageRow {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface Thread {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ThreadDetail extends Thread {
  messages: MessageRow[];
}

export interface UploadedFileAsset {
  filename: string;
  content_type: string;
  size: number;
  url: string;
}

export type ChatMode = "chat" | "sql" | "live";

export interface DataframeAskRequest {
  question: string;
  model?: string;
  google_sheet_url?: string;
  worksheet?: string;
  uploaded_file_url?: string;
  max_rows?: number;
}

export interface DataframeAskResponse {
  answer: string;
  row_count: number;
  columns: string[];
  source: string;
  intermediate_steps: string[];
}

