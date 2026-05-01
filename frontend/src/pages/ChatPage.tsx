import { Code2, Lightbulb, PenLine, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import InputBar from "../components/chat/InputBar";
import MessageList from "../components/chat/MessageList";
import { useChat } from "../hooks/useChat";

const SUGGESTIONS = [
  {
    icon: Code2,
    title: "Explain code",
    prompt: "Explain what this Python function does and how to improve it.",
  },
  {
    icon: PenLine,
    title: "Draft an email",
    prompt: "Draft a polite follow-up email to a client about a delayed deliverable.",
  },
  {
    icon: Lightbulb,
    title: "Brainstorm",
    prompt: "Give me five creative product names for an AI note-taking app.",
  },
  {
    icon: Sparkles,
    title: "Summarise",
    prompt: "Summarise the key ideas of LangChain LCEL in three bullet points.",
  },
];

export default function ChatPage() {
  const { messages, busy, error, send } = useChat();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  const onSend = async () => {
    const text = input;
    if (!text.trim()) return;
    setInput("");
    await send(text);
  };

  const empty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        {empty ? (
          <Hero onPick={(p) => setInput(p)} />
        ) : (
          <MessageList messages={messages} busy={busy} />
        )}
        {error && (
          <div className="mx-auto mb-4 max-w-3xl px-4">
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
              {error}
            </div>
          </div>
        )}
      </div>
      <InputBar value={input} busy={busy} onChange={setInput} onSend={onSend} />
    </div>
  );
}

function Hero({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-500 to-fuchsia-500 shadow-2xl shadow-accent-500/40">
        <Sparkles className="h-7 w-7 text-white" strokeWidth={2.4} />
      </div>
      <h1 className="bg-gradient-to-br from-white via-slate-200 to-slate-400 bg-clip-text text-3xl font-semibold tracking-tight text-transparent sm:text-4xl">
        How can I help you today?
      </h1>
      <p className="mt-3 max-w-md text-sm text-slate-400">
        Ask anything — code, ideas, summaries, drafts. Powered by the Amzur LiteLLM gateway.
      </p>
      <div className="mt-10 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s.title}
            onClick={() => onPick(s.prompt)}
            className="group flex items-start gap-3 rounded-xl border border-white/10 bg-white/5 p-4 text-left transition hover:-translate-y-0.5 hover:border-accent-500/40 hover:bg-white/10"
          >
            <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10 text-accent-400 transition group-hover:bg-accent-500/20">
              <s.icon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium text-slate-100">{s.title}</div>
              <div className="truncate text-xs text-slate-400">{s.prompt}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
