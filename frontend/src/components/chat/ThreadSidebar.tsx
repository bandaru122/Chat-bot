import { LogOut, MessageSquarePlus, Pencil, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuthStore } from "../../lib/authStore";
import { useChatStore } from "../../lib/chatStore";

export default function ThreadSidebar() {
  const threads = useChatStore((s) => s.threads);
  const activeId = useChatStore((s) => s.activeId);
  const loadThreads = useChatStore((s) => s.loadThreads);
  const selectThread = useChatStore((s) => s.selectThread);
  const createThread = useChatStore((s) => s.createThread);
  const deleteThread = useChatStore((s) => s.deleteThread);
  const renameThread = useChatStore((s) => s.renameThread);
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  useEffect(() => {
    loadThreads();
  }, [loadThreads]);

  const handleStartEdit = (id: string, currentTitle: string) => {
    setEditingId(id);
    setEditText(currentTitle);
  };

  const handleSaveEdit = async (id: string) => {
    if (editText.trim()) {
      await renameThread(id, editText.trim());
    }
    setEditingId(null);
    setEditText("");
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditText("");
  };

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-white/5 bg-ink-900/60 backdrop-blur-xl">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent-500 to-fuchsia-500 shadow-lg shadow-accent-500/30">
          <Sparkles className="h-4 w-4 text-white" strokeWidth={2.5} />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-tight">Amzur AI</div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">
            Chat
          </div>
        </div>
      </div>

      <div className="px-3">
        <button
          onClick={() => createThread()}
          className="group flex w-full items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium text-slate-100 transition hover:border-accent-500/50 hover:bg-white/10"
        >
          <MessageSquarePlus className="h-4 w-4 text-accent-400" />
          New chat
        </button>
      </div>

      <div className="mt-4 px-3 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Threads
      </div>
      <nav className="mt-2 flex-1 space-y-1 overflow-y-auto px-2 pb-4">
        {threads.length === 0 && (
          <div className="px-3 py-6 text-center text-xs text-slate-500">
            No conversations yet.
          </div>
        )}
        {threads.map((t) => {
          const isActive = t.id === activeId;
          const isEditing = editingId === t.id;

          return (
            <div key={t.id}>
              {isEditing ? (
                <div className="flex gap-2 rounded-lg bg-white/10 px-3 py-2">
                  <input
                    type="text"
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSaveEdit(t.id);
                      if (e.key === "Escape") handleCancelEdit();
                    }}
                    autoFocus
                    className="flex-1 border-0 bg-transparent text-sm text-white placeholder-slate-500 outline-none"
                    placeholder="Enter new title..."
                  />
                  <button
                    onClick={() => handleSaveEdit(t.id)}
                    className="text-xs font-medium text-accent-400 hover:text-accent-300"
                  >
                    Save
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="text-xs font-medium text-slate-400 hover:text-slate-300"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div
                  className={
                    "group flex cursor-pointer flex-col gap-1 rounded-lg px-3 py-2 text-sm transition " +
                    (isActive
                      ? "bg-white/10 text-white"
                      : "text-slate-300 hover:bg-white/5 hover:text-white")
                  }
                  onClick={() => selectThread(t.id)}
                >
                  <div className="flex items-center gap-2">
                    <span className="truncate flex-1">{t.title || "Untitled"}</span>
                    <div className="ml-auto flex gap-1 opacity-0 transition group-hover:opacity-100">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStartEdit(t.id, t.title);
                        }}
                        className="p-1"
                        title="Rename chat"
                      >
                        <Pencil className="h-3.5 w-3.5 text-slate-400 hover:text-accent-400" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteThread(t.id);
                        }}
                        className="p-1"
                        title="Delete chat"
                      >
                        <Trash2 className="h-3.5 w-3.5 text-slate-400 hover:text-red-400" />
                      </button>
                    </div>
                  </div>
                  <div className="text-[10px] text-slate-500 opacity-0 transition group-hover:opacity-100">
                    {new Date(t.updated_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-white/5 px-4 py-3">
        <div className="flex items-center gap-2">
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              className="h-7 w-7 rounded-full"
              alt=""
            />
          ) : (
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-sky-500 to-indigo-500 text-xs font-semibold text-white">
              {(user?.full_name ?? user?.email ?? "?")[0].toUpperCase()}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-medium text-slate-200">
              {user?.full_name || user?.email}
            </div>
            {user?.full_name && (
              <div className="truncate text-[10px] text-slate-500">{user.email}</div>
            )}
          </div>
          <button
            onClick={logout}
            className="rounded p-1 text-slate-400 transition hover:bg-white/10 hover:text-white"
            title="Sign out"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
