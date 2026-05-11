import { ArrowUp, ImagePlus, Paperclip, Square, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface Props {
  value: string;
  busy?: boolean;
  placeholder?: string;
  files?: File[];
  onChange: (v: string) => void;
  onFilesChange: (files: File[]) => void;
  onSend: () => void;
  imageGenerateEnabled?: boolean;
  onToggleImageGenerate?: () => void;
  onValidationError?: (message: string | null) => void;
}

const ALLOWED_ATTACHMENT_EXTENSIONS = new Set([
  ".txt", ".md", ".csv", ".tsv", ".pdf", ".json", ".ipynb", ".doc", ".docx", ".xlsx", ".xls",
  ".html", ".xml", ".yaml", ".yml", ".tex", ".sql", ".py", ".js", ".jsx", ".ts", ".tsx", ".java",
  ".c", ".cpp", ".cs", ".go", ".rs", ".php", ".rb", ".sh", ".srt", ".vtt", ".png", ".jpg", ".jpeg",
  ".webp", ".gif", ".mp4", ".webm", ".mov",
]);

const BLOCKED_ATTACHMENT_EXTENSIONS = new Set([
  ".exe", ".dll", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".jar", ".app",
]);

function extensionOf(name: string): string {
  const idx = name.lastIndexOf(".");
  if (idx < 0) return "";
  return name.slice(idx).toLowerCase();
}

export default function InputBar({
  value,
  busy = false,
  placeholder,
  files = [],
  onChange,
  onFilesChange,
  onSend,
  imageGenerateEnabled = false,
  onToggleImageGenerate,
  onValidationError,
}: Props) {
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [localValidationError, setLocalValidationError] = useState<string | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(el.scrollHeight, 220) + "px";
  }, [value]);

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!busy && (value.trim() || files.length > 0)) onSend();
    }
  };

  const onFilePicked = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    if (selected.length === 0) return;

    const accepted: File[] = [];
    const rejectedNames: string[] = [];
    for (const f of selected) {
      const ext = extensionOf(f.name);
      if (!ext || BLOCKED_ATTACHMENT_EXTENSIONS.has(ext) || !ALLOWED_ATTACHMENT_EXTENSIONS.has(ext)) {
        rejectedNames.push(f.name);
        continue;
      }
      accepted.push(f);
    }

    if (rejectedNames.length > 0) {
      const shown = rejectedNames.slice(0, 3).join(", ");
      const suffix = rejectedNames.length > 3 ? ` and ${rejectedNames.length - 3} more` : "";
      const msg = `File is not supported: ${shown}${suffix}. Please upload a supported format.`;
      setLocalValidationError(msg);
      onValidationError?.(msg);
    } else {
      setLocalValidationError(null);
      onValidationError?.(null);
    }

    if (accepted.length > 0) {
      onFilesChange([...files, ...accepted]);
    }
    event.target.value = "";
  };

  const removeFile = (index: number) => {
    onFilesChange(files.filter((_, i) => i !== index));
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-6">
      <div className="group relative rounded-2xl border border-white/10 bg-slate-800/80 p-2 shadow-2xl shadow-black/40 backdrop-blur-xl transition focus-within:border-violet-500/60 focus-within:ring-2 focus-within:ring-violet-500/20">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={onFilePicked}
          accept=".txt,.md,.csv,.tsv,.pdf,.json,.ipynb,.doc,.docx,.xlsx,.xls,.html,.xml,.yaml,.yml,.tex,.sql,.py,.js,.jsx,.ts,.tsx,.java,.c,.cpp,.cs,.go,.rs,.php,.rb,.sh,.srt,.vtt,.png,.jpg,.jpeg,.webp,.gif,.mp4,.webm,.mov"
        />
        {files.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2 px-1 pt-1">
            {files.map((file, index) => (
              <span
                key={`${file.name}-${index}`}
                className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-200"
              >
                <Paperclip className="h-3 w-3 text-slate-400" />
                <span className="max-w-[160px] truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="rounded p-0.5 text-slate-400 hover:bg-white/10 hover:text-slate-200"
                  title="Remove file"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        )}
        {localValidationError && (
          <div className="mb-2 px-1 text-xs text-red-300">{localValidationError}</div>
        )}
        <div className="flex items-end gap-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            title="Add attachments"
            className="ml-1 mb-1 flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:bg-white/5 hover:text-slate-200"
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onToggleImageGenerate}
            title="Generate image from prompt"
            className={
              "mb-1 flex h-9 w-9 items-center justify-center rounded-lg transition " +
              (imageGenerateEnabled
                ? "bg-fuchsia-500/20 text-fuchsia-300 ring-1 ring-fuchsia-400/40"
                : "text-slate-400 hover:bg-white/5 hover:text-slate-200")
            }
          >
            <ImagePlus className="h-4 w-4" />
          </button>
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKey}
            rows={1}
            placeholder={
              placeholder ??
              (imageGenerateEnabled ? "Describe the image you want to generate..." : "Message AI...")
            }
            className="max-h-56 min-h-[2.25rem] flex-1 resize-none bg-transparent px-1 py-2 text-[15px] text-slate-100 placeholder:text-slate-500 focus:outline-none"
          />
          <button
            onClick={onSend}
            disabled={busy || (!value.trim() && files.length === 0)}
            className="mb-1 flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 text-white shadow-lg shadow-violet-500/30 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none disabled:brightness-75"
            title={busy ? "Generating..." : imageGenerateEnabled ? "Generate image" : "Send (Enter)"}
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
        AI may produce inaccurate information. Press{" "}
        <kbd className="rounded bg-white/10 px-1 py-0.5 text-[10px]">Enter</kbd> to send,{" "}
        <kbd className="rounded bg-white/10 px-1 py-0.5 text-[10px]">Shift</kbd>+
        <kbd className="rounded bg-white/10 px-1 py-0.5 text-[10px]">Enter</kbd> for newline.
      </div>
    </div>
  );
}

