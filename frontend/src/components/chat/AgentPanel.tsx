import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../../lib/api";

type AgentEvent = {
  type: "thinking" | "tool_start" | "tool_end" | "final" | "error" | string;
  data: Record<string, unknown>;
};

type AgentStep = {
  tool: string;
  tool_input: unknown;
  log: string;
  observation: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
};

export function AgentPanel({ open, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [answer, setAnswer] = useState<string>("");
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // The agent emits many `thinking` events; rather than rendering each one as a
  // separate card (which clutters the UI and lingers after the final answer),
  // we show ONE persistent "AI is thinking…" indicator while busy, and surface
  // only the most recent thought text inside it.
  const lastThought = (() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].type === "thinking") {
        const t = events[i].data;
        return String(t.thought ?? t.message ?? "");
      }
    }
    return "";
  })();

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events.length, answer, busy]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const reset = () => {
    setEvents([]);
    setAnswer("");
    setSteps([]);
    setError(null);
  };

  // Each panel open starts a fresh session. This avoids showing stale events
  // and previous answers when the user clicks Live Agent from a new chat.
  useEffect(() => {
    if (!open) return;
    abortRef.current?.abort();
    setBusy(false);
    setQuery("");
    reset();
  }, [open]);

  const run = useCallback(async () => {
    const q = query.trim();
    if (!q || busy) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    reset();
    setBusy(true);
    try {
      await api.agentChatStream(
        q,
        (ev) => {
          setEvents((prev) => [...prev, ev]);
          if (ev.type === "final") {
            setAnswer(String(ev.data.answer ?? ""));
            const s = (ev.data.steps as AgentStep[] | undefined) ?? [];
            setSteps(s);
            // Final answer arrived — clear the thinking indicator immediately.
            setBusy(false);
          } else if (ev.type === "error") {
            setError(String(ev.data.message ?? "Agent error"));
            setBusy(false);
          }
        },
        ac.signal
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError((err as Error).message ?? "Network error");
      }
    } finally {
      setBusy(false);
    }
  }, [query, busy]);

  const stop = () => {
    abortRef.current?.abort();
    setBusy(false);
  };

  if (!open) return null;

  // Tool events render as visible cards; thinking events fold into the spinner.
  const toolEvents = events.filter(
    (ev) => ev.type === "tool_start" || ev.type === "tool_end"
  );

  const panel = (
    <div className="fixed inset-0 z-[1000] flex items-stretch justify-end bg-black/40 backdrop-blur-sm">
      <div className="flex h-full w-full max-w-2xl flex-col border-l border-white/10 bg-slate-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-white">Live Agent</div>
            <div className="text-xs text-slate-400">
              Ask agent to perform any task.
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-300 hover:bg-white/10"
          >
            Close
          </button>
        </div>

        <div className="border-b border-white/10 px-4 py-3">
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void run();
              }
            }}
            placeholder="Ask anything to Agent"
            rows={2}
            className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-400/50 focus:outline-none"
            disabled={busy}
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="text-[11px] text-slate-500">
              The agent decides which tools to call. Multiple tools can fire per query.
            </div>
            <div className="flex gap-2">
              {busy ? (
                <button
                  type="button"
                  onClick={stop}
                  className="rounded-md border border-red-400/30 bg-red-500/10 px-3 py-1.5 text-xs font-semibold text-red-200 hover:bg-red-500/20"
                >
                  Stop
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => void run()}
                  disabled={!query.trim()}
                  className="rounded-md border border-accent-400/40 bg-accent-500/20 px-3 py-1.5 text-xs font-semibold text-accent-100 hover:bg-accent-500/30 disabled:opacity-40"
                >
                  Run agent
                </button>
              )}
            </div>
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 text-sm">
          {events.length === 0 && !busy && !answer && (
            <div className="mt-10 text-center text-xs text-slate-500">
              Ask the agent something. You'll see its thinking, tool calls, and observations live.
            </div>
          )}

          <ul className="space-y-2">
            {toolEvents.map((ev, i) => (
              <li key={i}>
                <EventCard ev={ev} />
              </li>
            ))}
          </ul>

          {/* Persistent "AI is thinking…" indicator — visible only while busy
              (and disappears the moment the final answer or an error arrives). */}
          {busy && (
            <div className="mt-2 flex items-start gap-2 rounded border border-white/5 bg-white/[0.03] px-3 py-2 text-xs text-slate-300">
              <Spinner />
              <div className="whitespace-pre-wrap">
                {lastThought
                  ? `${lastThought}`
                  : "AI is thinking and fetching the data…"}
              </div>
            </div>
          )}

          {answer && (
            <div className="mt-4 rounded-lg border border-emerald-400/30 bg-emerald-500/5 px-3 py-3">
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
                Final answer
              </div>
              <div className="whitespace-pre-wrap text-justify text-slate-100">{answer}</div>
              {steps.length > 0 && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs text-slate-400 hover:text-slate-200">
                    Show {steps.length} tool {steps.length === 1 ? "call" : "calls"}
                  </summary>
                  <ol className="mt-2 space-y-2 text-xs text-slate-300">
                    {steps.map((s, i) => (
                      <li
                        key={i}
                        className="rounded border border-white/10 bg-white/5 p-2"
                      >
                        <div className="font-mono text-accent-300">
                          {i + 1}. {s.tool}({stringify(s.tool_input)})
                        </div>
                        <div className="mt-1 whitespace-pre-wrap text-slate-400">
                          {s.observation}
                        </div>
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          )}

          {error && (
            <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(panel, document.body);
}

function EventCard({ ev }: { ev: AgentEvent }) {
  if (ev.type === "tool_start") {
    return (
      <div className="rounded border border-sky-400/30 bg-sky-500/5 px-3 py-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-sky-300">
          Calling tool
        </div>
        <div className="mt-1 font-mono text-xs text-sky-100">
          {String(ev.data.tool ?? "?")}({stringify(ev.data.input)})
        </div>
      </div>
    );
  }
  if (ev.type === "tool_end") {
    const obs = String(ev.data.observation ?? ev.data.output ?? "");
    return (
      <div className="rounded border border-white/10 bg-white/5 px-3 py-2">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Observation · {String(ev.data.tool ?? "")}
        </div>
        <div className="mt-1 whitespace-pre-wrap text-xs text-slate-300">
          {obs}
        </div>
      </div>
    );
  }
  return null;
}

function Spinner() {
  return (
    <span
      className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-slate-400 border-t-transparent"
      aria-label="loading"
    />
  );
}

function stringify(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

export default AgentPanel;
