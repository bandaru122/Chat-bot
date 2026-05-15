import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Loader2, PanelLeft } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ThreadSidebar from "./components/chat/ThreadSidebar";
import { api } from "./lib/api";
import { useAuthStore } from "./lib/authStore";
import { useSettingsStore } from "./lib/settingsStore";
import ChatPage from "./pages/ChatPage";
import LoginPage from "./pages/LoginPage";
import SheetQaPage from "./pages/SheetQaPage";

export default function App() {
  const user = useAuthStore((s) => s.user);
  const loading = useAuthStore((s) => s.loading);
  const checkSession = useAuthStore((s) => s.checkSession);

  useEffect(() => {
    checkSession();
  }, [checkSession]);

  if (loading) {
    return (
      <div className="app-backdrop flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-accent-400" />
      </div>
    );
  }

  if (!user) return <LoginPage />;
  return <AuthenticatedApp />;
}

function AuthenticatedApp() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
  });

  const loadAvailableModels = useSettingsStore((s) => s.loadAvailableModels);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeView, setActiveView] = useState<"chat" | "sheet-qa">("chat");

  useEffect(() => {
    loadAvailableModels();
  }, [loadAvailableModels]);

  return (
    <div className="app-backdrop flex h-full min-h-0 w-full">
      <ThreadSidebar
        collapsed={sidebarCollapsed}
        activeView={activeView}
        onSelectView={setActiveView}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          env={health?.environment}
          online={!!health}
          onToggleSidebar={() => setSidebarCollapsed((v) => !v)}
        />
        <main className="min-h-0 flex-1 overflow-hidden">
          {activeView === "chat" ? (
            <ChatPage />
          ) : (
            <SheetQaPage onBackToChat={() => setActiveView("chat")} />
          )}
        </main>
      </div>
    </div>
  );
}

function TopBar({
  env,
  online,
  onToggleSidebar,
}: {
  env?: string;
  online: boolean;
  onToggleSidebar: () => void;
}) {
  const selectedModel = useSettingsStore((s) => s.selectedModel);
  const availableModels = useSettingsStore((s) => s.availableModels);
  const setSelectedModel = useSettingsStore((s) => s.setSelectedModel);
  const currentModel = availableModels.find((m) => m.id === selectedModel);
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false);
  const modelMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!modelMenuRef.current) return;
      if (event.target instanceof Node && !modelMenuRef.current.contains(event.target)) {
        setIsModelMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <header className="flex items-center justify-between gap-4 border-b border-white/5 bg-ink-900/40 px-6 py-3 backdrop-blur-xl">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onToggleSidebar}
          className="rounded-lg border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10 hover:text-white"
          title="Toggle sidebar"
        >
          <PanelLeft className="h-4 w-4" />
        </button>
        <div className="hidden items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 sm:flex">
        <span
          className={
            "h-2 w-2 rounded-full " + (online ? "bg-emerald-400" : "bg-red-400")
          }
        />
        <span className="font-medium">{currentModel?.name ?? "connecting…"}</span>
        {env && (
          <>
            <span className="text-slate-600">·</span>
            <span className="text-slate-400">{env}</span>
          </>
        )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div className="text-xs text-slate-500">Model:</div>
        <div ref={modelMenuRef} className="relative">
          <button
            type="button"
            onClick={() => setIsModelMenuOpen((open) => !open)}
            className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm font-medium text-slate-100 transition hover:border-accent-500/50 hover:bg-white/10"
          >
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-accent-400"></span>
              {currentModel?.name || "Select model"}
            </span>
            <ChevronDown
              className={
                "h-3.5 w-3.5 text-slate-400 transition-transform " +
                (isModelMenuOpen ? "rotate-180" : "rotate-0")
              }
            />
          </button>
          <div
            className={
              "absolute right-0 top-full z-50 mt-1 w-56 rounded-lg border border-white/10 bg-ink-950/90 shadow-xl backdrop-blur-xl max-h-96 overflow-y-auto " +
              (isModelMenuOpen ? "block" : "hidden")
            }
          >
            {availableModels.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  setSelectedModel(m.id);
                  setIsModelMenuOpen(false);
                }}
                className={
                  "w-full px-4 py-2.5 text-left text-sm transition " +
                  (selectedModel === m.id
                    ? "bg-accent-500/20 text-accent-300"
                    : "text-slate-300 hover:bg-white/5 hover:text-white")
                }
              >
                <div className="font-medium">{m.name}</div>
                <div className="text-xs text-slate-500">{m.provider}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}
