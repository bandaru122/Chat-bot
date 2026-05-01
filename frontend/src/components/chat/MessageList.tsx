import { Bot, Edit2, User } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChatStore } from "../../lib/chatStore";
import type { MessageRow } from "../../types";
import CodeBlock from "./CodeBlock";

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
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 py-8">
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
              id={m.id}
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
            <div className="flex items-center gap-1 rounded-2xl bg-white/5 px-4 py-3">
              <Dot />
              <Dot delay="150ms" />
              <Dot delay="300ms" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Dot({ delay }: { delay?: string }) {
  return (
    <span
      className="h-1.5 w-1.5 rounded-full bg-slate-400"
      style={{ animation: "blink 1.2s infinite", animationDelay: delay }}
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
  id,
  role,
  content,
  timestamp,
  onEdit,
}: {
  id: string;
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
          {isUser ? "You" : "Amzur AI"}
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
      <div className="prose prose-invert prose-sm max-w-none prose-p:text-justify prose-p:leading-relaxed prose-headings:mt-2 prose-headings:mb-2 prose-pre:bg-transparent prose-pre:p-0 prose-pre:m-0 prose-code:before:content-none prose-code:after:content-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            img({ src, alt }) {
              return (
                <img
                  src={src}
                  alt={alt || "Generated image"}
                  className="max-w-full h-auto rounded-lg my-2 shadow-lg"
                  style={{ maxWidth: "100%", maxHeight: "400px" }}
                />
              );
            },
            a({ href, children }) {
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
            code({ className, children, ...rest }) {
              const match = /language-(\w+)/.exec(className || "");
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
          {content}
        </ReactMarkdown>
      </div>
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

