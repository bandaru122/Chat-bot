import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Loader2 } from "lucide-react";
import { useEffect } from "react";
import ThreadSidebar from "./components/chat/ThreadSidebar";
import { api } from "./lib/api";
import { useAuthStore } from "./lib/authStore";
import { useSettingsStore } from "./lib/settingsStore";
import ChatPage from "./pages/ChatPage";
import LoginPage from "./pages/LoginPage";

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

  useEffect(() => {
    loadAvailableModels();
  }, [loadAvailableModels]);

  return (
    <div className="app-backdrop flex h-full min-h-0 w-full">
      <ThreadSidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar model={health?.llm_model} env={health?.environment} online={!!health} />
        <main className="min-h-0 flex-1 overflow-hidden">
          <ChatPage />
        </main>
      </div>
    </div>
  );
}

function TopBar({
  model,
  env,
  online,
}: {
  model?: string;
  env?: string;
  online: boolean;
}) {
  const selectedModel = useSettingsStore((s) => s.selectedModel);
  const availableModels = useSettingsStore((s) => s.availableModels);
  const setSelectedModel = useSettingsStore((s) => s.setSelectedModel);
  const currentModel = availableModels.find((m) => m.id === selectedModel);

  return (
    <header className="flex items-center justify-between gap-4 border-b border-white/5 bg-ink-900/40 px-6 py-3 backdrop-blur-xl">
      <div className="hidden items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 sm:flex">
        <span
          className={
            "h-2 w-2 rounded-full " + (online ? "bg-emerald-400" : "bg-red-400")
          }
        />
        <span className="font-medium">{model ?? "connecting…"}</span>
        {env && (
          <>
            <span className="text-slate-600">·</span>
            <span className="text-slate-400">{env}</span>
          </>
        )}
      </div>

      <div className="flex items-center gap-3">
        <div className="text-xs text-slate-500">Model:</div>
        <div className="group relative">
          <button className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm font-medium text-slate-100 transition hover:border-accent-500/50 hover:bg-white/10">
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-accent-400"></span>
              {currentModel?.name || "Select model"}
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
          </button>
          <div className="absolute right-0 top-full mt-1 hidden w-56 rounded-lg border border-white/10 bg-ink-950/90 shadow-xl backdrop-blur-xl group-hover:block z-50">
            {availableModels.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelectedModel(m.id)}
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
