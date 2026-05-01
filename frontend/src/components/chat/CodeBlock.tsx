import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

interface Props {
  language: string;
  code: string;
}

export default function CodeBlock({ language, code }: Props) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1400);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-white/10 bg-slate-950/80">
      <div className="flex items-center justify-between border-b border-white/10 bg-white/5 px-3 py-1.5 text-xs">
        <span className="font-mono text-[11px] uppercase tracking-wider text-slate-400">
          {language || "code"}
        </span>
        <button
          onClick={onCopy}
          className="flex items-center gap-1 rounded px-2 py-0.5 text-slate-300 transition hover:bg-white/10 hover:text-white"
        >
          {copied ? (
            <>
              <Check className="h-3.5 w-3.5 text-emerald-400" /> Copied
            </>
          ) : (
            <>
              <Copy className="h-3.5 w-3.5" /> Copy
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        style={oneDark}
        customStyle={{
          margin: 0,
          padding: "0.9rem 1rem",
          background: "transparent",
          fontSize: "0.85rem",
          lineHeight: 1.55,
        }}
        codeTagProps={{ style: { fontFamily: "JetBrains Mono, monospace" } }}
      >
        {code.replace(/\n$/, "")}
      </SyntaxHighlighter>
    </div>
  );
}

