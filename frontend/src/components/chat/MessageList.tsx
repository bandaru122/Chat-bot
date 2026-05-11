import { Bot, Edit2, User } from "lucide-react";
import { useState } from "react";
import rehypeKatex from "rehype-katex";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { useChatStore } from "../../lib/chatStore";
import type { MessageRow } from "../../types";
import ChartCard from "./ChartCard";
import CodeBlock from "./CodeBlock";
import MermaidBlock from "./MermaidBlock";
import TableCard from "./TableCard";
import VideoEmbed from "./VideoEmbed";

interface ChartPayload {
  type: "chart";
  chartType: "bar" | "line" | "pie";
  title: string;
  labels: string[];
  data: number[];
  xAxisLabel?: string;
  yAxisLabel?: string;
}

interface TablePayload {
  type: "table";
  title: string;
  columns: string[];
  rows: Array<Array<string | number | boolean | null>>;
}

interface TextPayload {
  type: "text";
  content: string;
}

function parseStructuredContent(content: string): ChartPayload | TablePayload | TextPayload | null {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>;
    if (
      parsed.type === "chart" &&
      (parsed.chartType === "bar" || parsed.chartType === "line" || parsed.chartType === "pie") &&
      Array.isArray(parsed.labels) &&
      Array.isArray(parsed.data)
    ) {
      return {
        type: "chart",
        chartType: parsed.chartType,
        title: typeof parsed.title === "string" ? parsed.title : "Chart",
        labels: parsed.labels.map((value) => String(value)),
        data: parsed.data.map((value) => Number(value)),
        xAxisLabel: typeof parsed.xAxisLabel === "string" ? parsed.xAxisLabel : "",
        yAxisLabel: typeof parsed.yAxisLabel === "string" ? parsed.yAxisLabel : "",
      };
    }

    if (
      parsed.type === "table" &&
      Array.isArray(parsed.columns) &&
      Array.isArray(parsed.rows) &&
      parsed.rows.every((row) => Array.isArray(row))
    ) {
      return {
        type: "table",
        title: typeof parsed.title === "string" ? parsed.title : "Table",
        columns: parsed.columns.map((column) => String(column)),
        rows: parsed.rows.map((row) =>
          (row as unknown[]).map((cell) => {
            if (
              typeof cell === "string" ||
              typeof cell === "number" ||
              typeof cell === "boolean" ||
              cell === null
            ) {
              return cell;
            }
            return String(cell);
          })
        ),
      };
    }

    if (parsed.type === "text" && typeof parsed.content === "string") {
      return {
        type: "text",
        content: parsed.content,
      };
    }

    return null;
  } catch {
    return null;
  }
}

function extractVideoUrls(content: string): string[] {
  const matches = content.match(/https?:\/\/[^\s)\]>"']+/gi) ?? [];
  const unique = new Set<string>();

  for (const match of matches) {
    const cleaned = match.replace(/[)>.,;!?]+$/g, "");
    if (isHostedVideoUrl(cleaned) || isVideoUrl(cleaned)) {
      unique.add(cleaned);
    }
  }

  return [...unique];
}

function isVideoUrl(url: string) {
  return /\.(mp4|webm|ogg|mov|m4v)(\?|#|$)/i.test(url) || url.startsWith("data:video/");
}

function isHostedVideoUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace("www.", "");
    return (
      host === "youtu.be" ||
      host === "youtube.com" ||
      host === "m.youtube.com" ||
      host === "vimeo.com" ||
      host === "player.vimeo.com"
    );
  } catch {
    return false;
  }
}

interface Props {
  messages: MessageRow[];
  busy?: boolean;
}

export default function MessageList({ messages, busy }: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const editMessage = useChatStore((s) => s.editMessage);
  const loading = useChatStore((s) => s.loading);

  const handleStartEdit = (id: string, content: string) => {
    setEditingId(id);
    setEditText(content);
  };

  const handleSaveEdit = async (id: string) => {
    if (editText.trim()) {
      await editMessage(id, editText.trim());
      setEditingId(null);
      setEditText("");
    }
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditText("");
  };

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-3 py-4 sm:px-4 sm:py-5">
      {messages.map((m) => (
        <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
          {editingId === m.id ? (
            <div className="flex w-full max-w-2xl gap-3">
              {m.role === "assistant" && <Avatar role="assistant" />}
              <div className="flex-1 rounded-2xl bg-white/5 px-4 py-3">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  Edit message
                </div>
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && e.ctrlKey) handleSaveEdit(m.id);
                    if (e.key === "Escape") handleCancelEdit();
                  }}
                  autoFocus
                  className="w-full border-0 bg-transparent text-[15px] leading-relaxed text-white outline-none placeholder-slate-500 resize-none"
                  rows={3}
                  placeholder="Edit your message..."
                />
                <div className="mt-2 flex gap-2">
                  <button
                    onClick={() => handleSaveEdit(m.id)}
                    disabled={loading}
                    className="text-xs font-medium text-accent-400 hover:text-accent-300 disabled:opacity-50"
                  >
                    Save (Ctrl+Enter)
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="text-xs font-medium text-slate-400 hover:text-slate-300"
                  >
                    Cancel
                  </button>
                </div>
              </div>
              {m.role === "user" && <Avatar role="user" />}
            </div>
          ) : (
            <Bubble
              role={m.role}
              content={m.content}
              timestamp={m.created_at}
              onEdit={() => handleStartEdit(m.id, m.content)}
            />
          )}
        </div>
      ))}
      {busy && (
        <div className="flex justify-start">
          <div className="flex items-start gap-3 animate-fade-in-up">
            <Avatar role="assistant" />
            <div className="flex items-center gap-2 rounded-2xl bg-white/5 px-4 py-3">
              <ThinkingSpinner />
              <span className="text-sm text-slate-300">AI is thinking…</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ThinkingSpinner() {
  return (
    <span
      className="inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-slate-400 border-t-transparent"
      aria-label="loading"
    />
  );
}
function Avatar({ role }: { role: string }) {
  if (role === "user") {
    return (
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-sky-500 to-indigo-500 text-white shadow-lg shadow-sky-500/20">
        <User className="h-4 w-4" strokeWidth={2.4} />
      </div>
    );
  }
  return (
    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-lg shadow-violet-500/30">
      <Bot className="h-4 w-4" strokeWidth={2.4} />
    </div>
  );
}

function Bubble({
  role,
  content,
  timestamp,
  onEdit,
}: {
  role: string;
  content: string;
  timestamp: string;
  onEdit: () => void;
}) {
  const isUser = role === "user";
  const date = new Date(timestamp);
  const timeStr = date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
  const dateStr = date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const structuredContent = !isUser ? parseStructuredContent(content) : null;
  const chartPayload = structuredContent?.type === "chart" ? structuredContent : null;
  const tablePayload = structuredContent?.type === "table" ? structuredContent : null;
  const markdownContent = structuredContent?.type === "text" ? structuredContent.content : content;
  const detectedVideoUrls = !isUser ? extractVideoUrls(markdownContent) : [];

  const bubbleContent = (
    <div
      className={
        "min-w-0 flex-1 rounded-2xl px-4 py-3 text-[15px] leading-relaxed text-justify " +
        (isUser
          ? "bg-gradient-to-br from-indigo-600/30 to-violet-600/30 ring-1 ring-inset ring-white/10"
          : "bg-white/5 ring-1 ring-inset ring-white/5")
      }
    >
      <div className="mb-1 flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          {isUser ? "You" : "AI"}
        </div>
        {isUser && (
          <button
            onClick={onEdit}
            className="p-1 opacity-0 transition group-hover:opacity-100"
            title="Edit message"
          >
            <Edit2 className="h-3.5 w-3.5 text-slate-400 hover:text-accent-400" />
          </button>
        )}
      </div>
      {chartPayload ? (
        <ChartCard payload={chartPayload} />
      ) : tablePayload ? (
        <TableCard payload={tablePayload} />
      ) : (
        <div className="prose prose-invert prose-sm max-w-none prose-p:text-justify prose-p:leading-relaxed prose-headings:mt-2 prose-headings:mb-2 prose-pre:bg-transparent prose-pre:p-0 prose-pre:m-0 prose-code:before:content-none prose-code:after:content-none prose-img:max-w-lg prose-img:h-auto prose-img:rounded-lg prose-img:my-2 prose-img:shadow-lg prose-table:block prose-table:overflow-x-auto prose-th:border prose-th:border-white/20 prose-th:bg-white/5 prose-th:px-3 prose-th:py-2 prose-td:border prose-td:border-white/10 prose-td:px-3 prose-td:py-2">
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeKatex]}
            components={{
              img({ src, alt }) {
                if (!src) return null;
                return (
                  <img
                    src={src}
                    alt={alt || "Generated image"}
                    className="block w-full max-w-lg h-auto rounded-lg my-2 shadow-lg"
                    style={{ display: "block", maxWidth: "100%", maxHeight: "500px", objectFit: "contain" }}
                  />
                );
              },
              a({ href, children }) {
                if (!href) return <>{children}</>;

                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-accent-400 hover:text-accent-300 underline"
                  >
                    {children}
                  </a>
                );
              },
              p({ children }) {
                return <p className="text-justify leading-relaxed my-1">{children}</p>;
              },
              table({ children }) {
                return (
                  <div className="my-3 w-full overflow-x-auto rounded-lg border border-white/10">
                    <table className="w-full min-w-[520px] border-collapse text-sm">{children}</table>
                  </div>
                );
              },
              thead({ children }) {
                return <thead className="bg-white/5">{children}</thead>;
              },
              th({ children }) {
                return (
                  <th className="border border-white/20 px-3 py-2 text-left font-semibold text-slate-200">
                    {children}
                  </th>
                );
              },
              td({ children }) {
                return <td className="border border-white/10 px-3 py-2 text-slate-200">{children}</td>;
              },
              code({ className, children, ...rest }) {
                const match = /language-(\w+)/.exec(className || "");
                const language = (match?.[1] ?? "").toLowerCase();
                const isBlock =
                  (
                    rest as {
                      node?: {
                        position?: {
                          start: { line: number };
                          end: { line: number };
                        };
                      };
                    }
                  ).node?.position?.start.line !==
                  (
                    rest as {
                      node?: {
                        position?: {
                          start: { line: number };
                          end: { line: number };
                        };
                      };
                    }
                  ).node?.position?.end.line;
                const text = String(children ?? "");
                if (language === "mermaid") {
                  return <MermaidBlock code={text} />;
                }
                if (match || isBlock) {
                  return <CodeBlock language={match?.[1] ?? ""} code={text} />;
                }
                return (
                  <code className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[0.85em] text-violet-400">
                    {children}
                  </code>
                );
              },
            }}
          >
            {markdownContent}
          </ReactMarkdown>

          {detectedVideoUrls.length > 0 && (
            <div className="mt-3 space-y-3">
              {detectedVideoUrls.map((videoUrl) => (
                <VideoEmbed key={videoUrl} url={videoUrl} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );

  const timestamp_display = (
    <div className="text-[10px] text-slate-500 opacity-0 transition group-hover:opacity-100">
      <span>{dateStr}</span>
      <span className="mx-1">·</span>
      <span>{timeStr}</span>
    </div>
  );

  if (isUser) {
    return (
      <div className="group flex w-full max-w-2xl flex-col items-end gap-1 animate-fade-in-up ml-auto">
        <div className="flex items-start gap-3">
          {bubbleContent}
          <Avatar role={role} />
        </div>
        {timestamp_display}
      </div>
    );
  }

  return (
    <div className="group flex w-full max-w-2xl flex-col items-start gap-1 animate-fade-in-up">
      <div className="flex items-start gap-3">
        <Avatar role={role} />
        {bubbleContent}
      </div>
      {timestamp_display}
    </div>
  );
}

