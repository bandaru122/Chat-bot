import { Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Note } from "../types";

export default function NotesPage() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api.listNotes().then(setNotes).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.createNote(title, content);
      setTitle("");
      setContent("");
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const summarize = async (id: number) => {
    setBusy(true);
    try {
      await api.summarize(id);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: number) => {
    setBusy(true);
    try {
      await api.deleteNote(id);
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="mx-auto max-w-3xl space-y-6 px-6 py-8">
      <div className="space-y-3 rounded-2xl border border-white/10 bg-slate-800/60 p-4 backdrop-blur-xl">
        <input
          className="w-full rounded-lg border border-white/10 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-violet-500/60 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
          placeholder="Title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          className="w-full resize-y rounded-lg border border-white/10 bg-slate-900/60 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-violet-500/60 focus:outline-none focus:ring-2 focus:ring-violet-500/20"
          placeholder="Write a quick noteâ€¦"
          rows={4}
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <button
          onClick={create}
          disabled={busy || !title.trim()}
          className="rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-violet-500/30 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40 disabled:brightness-75"
        >
          {busy ? "Savingâ€¦" : "Add note"}
        </button>
      </div>
      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}
      <ul className="space-y-3">
        {notes.map((n) => (
          <li
            key={n.id}
            className="rounded-2xl border border-white/10 bg-slate-800/60 p-4 backdrop-blur-xl"
          >
            <h3 className="text-base font-semibold text-slate-100">{n.title}</h3>
            <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
              {n.content}
            </p>
            {n.summary && (
              <blockquote className="mt-3 rounded-lg border-l-2 border-violet-500 bg-white/5 p-3 text-sm text-slate-300">
                <span className="text-xs font-semibold uppercase tracking-wider text-violet-400">
                  Summary
                </span>
                <p className="mt-1">{n.summary}</p>
              </blockquote>
            )}
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => summarize(n.id)}
                disabled={busy}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-violet-500/40 hover:bg-white/10 disabled:opacity-40"
              >
                <Sparkles className="h-3.5 w-3.5 text-violet-400" />
                Summarize
              </button>
              <button
                onClick={() => remove(n.id)}
                disabled={busy}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-300 disabled:opacity-40"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </button>
            </div>
          </li>
        ))}
        {notes.length === 0 && (
          <li className="rounded-2xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-500">
            No notes yet â€” write your first one above.
          </li>
        )}
      </ul>
    </section>
  );
}

