import { ArrowLeft, Loader2, Table2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../lib/api";
import { useSettingsStore } from "../lib/settingsStore";
import type { DataframeAskResponse } from "../types";

interface Props {
  onBackToChat: () => void;
}

export default function SheetQaPage({ onBackToChat }: Props) {
  const selectedModel = useSettingsStore((s) => s.selectedModel);
  const [sheetUrl, setSheetUrl] = useState("");
  const [worksheet, setWorksheet] = useState("0");
  const [question, setQuestion] = useState("");
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploadedFileUrl, setUploadedFileUrl] = useState<string | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const [result, setResult] = useState<DataframeAskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = useMemo(() => {
    return question.trim().length > 0 && (sheetUrl.trim().length > 0 || !!uploadedFileUrl);
  }, [question, sheetUrl, uploadedFileUrl]);

  const onPickFile = async (file: File | null) => {
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const assets = await api.uploadFiles([file]);
      const first = assets[0];
      if (!first) throw new Error("Upload returned no file metadata");
      setUploadedFileUrl(first.url);
      setUploadedFileName(first.filename);
      setSheetUrl("");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  };

  const onAsk = async () => {
    if (!canSubmit || busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await api.dataframeAsk({
        question: question.trim(),
        model: selectedModel,
        google_sheet_url: sheetUrl.trim() || undefined,
        worksheet: worksheet.trim() || "0",
        uploaded_file_url: uploadedFileUrl || undefined,
        max_rows: 2000,
      });
      setResult(response);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex h-full w-full max-w-5xl flex-col gap-4 overflow-y-auto px-4 py-4 sm:px-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-300">
            <Table2 className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-slate-100">Spreadsheet Q&A</h1>
            <p className="text-xs text-slate-400">Ask questions over CSV, XLSX, or Google Sheets data.</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onBackToChat}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Chat
        </button>
      </div>

      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <label className="md:col-span-2">
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Google Sheet URL</div>
            <textarea
              value={sheetUrl}
              onChange={(e) => {
                setSheetUrl(e.target.value);
                if (e.target.value.trim()) {
                  setUploadedFileUrl(null);
                  setUploadedFileName(null);
                }
              }}
              placeholder="https://docs.google.com/spreadsheets/d/..."
              rows={3}
              className="w-full resize-y rounded-lg border border-white/10 bg-ink-900/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-emerald-400/40"
            />
          </label>

          <label>
            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Worksheet</div>
            <input
              value={worksheet}
              onChange={(e) => setWorksheet(e.target.value)}
              placeholder="0"
              className="mb-3 w-full rounded-lg border border-white/10 bg-ink-900/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-emerald-400/40"
            />

            <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Or Upload File</div>
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(e) => void onPickFile(e.target.files?.[0] ?? null)}
              className="w-full text-xs text-slate-300 file:mr-3 file:rounded-md file:border file:border-white/10 file:bg-white/10 file:px-2.5 file:py-1.5 file:text-xs file:text-slate-200"
            />
            {uploadedFileName && (
              <div className="mt-2 text-xs text-emerald-300">Using uploaded file: {uploadedFileName}</div>
            )}
          </label>
        </div>

        <label className="mt-3 block">
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Question</div>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question about the sheet, e.g. What is the total sales by region?"
            rows={4}
            className="w-full resize-y rounded-lg border border-white/10 bg-ink-900/60 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-emerald-400/40"
          />
        </label>

        <div className="mt-3 flex items-center justify-end gap-2">
          {(uploading || busy) && <Loader2 className="h-4 w-4 animate-spin text-emerald-300" />}
          <button
            type="button"
            onClick={() => void onAsk()}
            disabled={!canSubmit || uploading || busy}
            className="rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-4 py-2 text-sm font-medium text-emerald-200 transition hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Analyzing..." : "Ask Dataframe Agent"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>
      )}

      {result && (
        <div className="space-y-3 rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="text-xs uppercase tracking-wide text-slate-400">Answer</div>
          <div className="whitespace-pre-wrap rounded-lg border border-white/10 bg-ink-900/50 p-3 text-sm text-slate-100">
            {result.answer}
          </div>

          <div className="grid grid-cols-1 gap-3 text-xs text-slate-300 sm:grid-cols-3">
            <div className="rounded-lg border border-white/10 bg-ink-900/40 p-2">
              <div className="text-slate-500">Source</div>
              <div>{result.source}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-ink-900/40 p-2">
              <div className="text-slate-500">Rows Loaded</div>
              <div>{result.row_count}</div>
            </div>
            <div className="rounded-lg border border-white/10 bg-ink-900/40 p-2">
              <div className="text-slate-500">Columns</div>
              <div>{result.columns.length}</div>
            </div>
          </div>

          {result.intermediate_steps.length > 0 && (
            <details className="rounded-lg border border-white/10 bg-ink-900/40 p-3">
              <summary className="cursor-pointer text-sm font-medium text-slate-200">Agent intermediate steps</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-300">
                {result.intermediate_steps.map((step, idx) => (
                  <li key={`${idx}-${step.slice(0, 20)}`}>{step}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
