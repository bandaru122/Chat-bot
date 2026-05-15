import { LogOut, MessageSquarePlus, Pencil, Search, Sparkles, Table2, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "../../lib/authStore";
import { useChatStore } from "../../lib/chatStore";

interface Props {
  collapsed: boolean;
  activeView: "chat" | "sheet-qa";
  onSelectView: (view: "chat" | "sheet-qa") => void;
}

export default function ThreadSidebar({ collapsed, activeView, onSelectView }: Props) {
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
  const [search, setSearch] = useState("");
  const loadedOnceRef = useRef(false);

  useEffect(() => {
    // React StrictMode runs mount effects twice in development.
    // Keep this idempotent so we don't fire overlapping load/select flows.
    if (loadedOnceRef.current) return;
    loadedOnceRef.current = true;
    void loadThreads();
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

  const filteredThreads = threads.filter((t) =>
    (t.title || "Untitled").toLowerCase().includes(search.trim().toLowerCase())
  );

  return (
    <aside
      className={
        "flex h-full shrink-0 flex-col border-r border-white/5 bg-ink-900/60 backdrop-blur-xl transition-all " +
        (collapsed ? "w-16" : "w-72")
      }
    >
      <div className={"flex items-center px-4 py-4 " + (collapsed ? "justify-center" : "gap-2")}> 
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent-500 to-fuchsia-500 shadow-lg shadow-accent-500/30">
          <Sparkles className="h-4 w-4 text-white" strokeWidth={2.5} />
        </div>
        {!collapsed && (
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">AI</div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Chat</div>
          </div>
        )}
      </div>

      <div className="px-3">
        <button
          onClick={() => {
            onSelectView("chat");
            createThread();
          }}
          className={
            "group flex w-full cursor-pointer items-center rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm font-medium text-slate-100 transition hover:border-accent-500/50 hover:bg-white/10 " +
            (collapsed ? "justify-center" : "gap-2")
          }
          title="New chat"
        >
          <MessageSquarePlus className="h-4 w-4 text-accent-400" />
          {!collapsed && "New chat"}
        </button>
      </div>

      {!collapsed && (
        <div className="mt-3 px-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-2.5 h-3.5 w-3.5 text-slate-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search chats"
              className="w-full rounded-lg border border-white/10 bg-white/5 py-2 pl-7 pr-2 text-xs text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-accent-500/40"
            />
          </div>
        </div>
      )}

      {!collapsed && (
        <div className="mt-3 px-3 text-[10px] font-semibold uppercase tracking-widest text-slate-500">
          Recent Chat
        </div>
      )}
      <nav className="mt-2 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
        {filteredThreads.length === 0 && !collapsed && (
          <div className="px-3 py-6 text-center text-xs text-slate-500">
            {threads.length === 0 ? "No conversations yet." : "No chats match your search."}
          </div>
        )}
        {filteredThreads.map((t) => {
          const isActive = t.id === activeId;
          const isEditing = editingId === t.id;

          return (
            <div key={t.id}>
              {isEditing && !collapsed ? (
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
                    "group flex cursor-pointer flex-col gap-0.5 rounded-lg px-2.5 py-1.5 text-sm transition " +
                    (isActive
                      ? "bg-white/10 text-white"
                      : "text-slate-300 hover:bg-white/5 hover:text-white")
                  }
                  onClick={() => {
                    onSelectView("chat");
                    selectThread(t.id);
                  }}
                >
                  <div className={"flex w-full items-center " + (collapsed ? "justify-center" : "gap-2")}> 
                    {!collapsed && <span className="truncate flex-1">{t.title || "Untitled"}</span>}
                    {collapsed && <span className="h-2 w-2 rounded-full bg-slate-400" />}
                    {!collapsed && <div className="ml-auto flex gap-1 opacity-0 transition group-hover:opacity-100">
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
                    </div>}
                  </div>
                  {!collapsed && <div className="text-[10px] text-slate-500">
                    {new Date(t.updated_at).toLocaleString("en-US", {
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: true,
                    })}
                  </div>}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      <div className="px-3 pb-3">
        <button
          type="button"
          onClick={() => onSelectView("sheet-qa")}
          className={
            "group flex w-full items-center rounded-lg border px-3 py-2 text-sm font-medium transition " +
            (activeView === "sheet-qa"
              ? "border-emerald-400/50 bg-emerald-500/15 text-emerald-200"
              : "border-white/10 bg-white/5 text-slate-200 hover:border-emerald-400/40 hover:bg-white/10") +
            (collapsed ? " justify-center" : " gap-2")
          }
          title="Spreadsheet Q&A"
        >
          <Table2 className="h-4 w-4" />
          {!collapsed && "Spreadsheet Q&A"}
        </button>
      </div>

      <div className="border-t border-white/5 px-4 py-3">
        <div className={"flex items-center " + (collapsed ? "justify-center" : "gap-2")}>
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
          {!collapsed && <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-medium text-slate-200">
              {user?.full_name || user?.email}
            </div>
            {user?.full_name && (
              <div className="truncate text-[10px] text-slate-500">{user.email}</div>
            )}
          </div>}
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
