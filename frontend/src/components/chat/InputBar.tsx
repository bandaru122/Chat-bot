import { ArrowUp, Paperclip, Square } from "lucide-react";
import { useEffect, useRef } from "react";

interface Props {
  value: string;
  busy?: boolean;
  placeholder?: string;
  onChange: (v: string) => void;
  onSend: () => void;
}

export default function InputBar({
  value,
  busy = false,
  placeholder,
  onChange,
  onSend,
}: Props) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(el.scrollHeight, 220) + "px";
  }, [value]);

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && value.trim()) onSend();
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-6">
      <div className="group relative rounded-2xl border border-white/10 bg-slate-800/80 p-2 shadow-2xl shadow-black/40 backdrop-blur-xl transition focus-within:border-violet-500/60 focus-within:ring-2 focus-within:ring-violet-500/20">
        <div className="flex items-end gap-2">
          <button
            type="button"
            disabled
            title="Attachments â€” coming soon"
            className="ml-1 mb-1 flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:bg-white/5 hover:text-slate-200 disabled:opacity-40"
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKey}
            rows={1}
            placeholder={placeholder ?? "Message Amzur AIâ€¦"}
            className="max-h-56 min-h-[2.25rem] flex-1 resize-none bg-transparent px-1 py-2 text-[15px] text-slate-100 placeholder:text-slate-500 focus:outline-none"
          />
          <button
            onClick={onSend}
            disabled={busy || !value.trim()}
            className="mb-1 flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-lg shadow-violet-500/30 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none disabled:brightness-75"
            title={busy ? "Generatingâ€¦" : "Send (Enter)"}
          >
            {busy ? (
              <Square className="h-3.5 w-3.5 fill-white" />
            ) : (
              <ArrowUp className="h-4 w-4" strokeWidth={2.6} />
            )}
          </button>
        </div>
      </div>
      <div className="mt-2 text-center text-[11px] text-slate-500">
        Amzur AI may produce inaccurate information. Press{" "}
        <kbd className="rounded bg-white/10 px-1 py-0.5 text-[10px]">Enter</kbd> to send,{" "}
        <kbd className="rounded bg-white/10 px-1 py-0.5 text-[10px]">Shift</kbd>+
        <kbd className="rounded bg-white/10 px-1 py-0.5 text-[10px]">Enter</kbd> for newline.
      </div>
    </div>
  );
}

