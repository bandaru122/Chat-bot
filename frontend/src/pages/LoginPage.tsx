import { KeyRound, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { useAuthStore } from "../lib/authStore";

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const login = useAuthStore((s) => s.login);
  const register = useAuthStore((s) => s.register);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, fullName || undefined);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-backdrop flex min-h-full items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-accent-500 to-fuchsia-500 shadow-2xl shadow-accent-500/40">
            <Sparkles className="h-7 w-7 text-white" strokeWidth={2.4} />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">
            Amzur AI Chat
          </h1>
          <p className="text-sm text-slate-400">
            Sign in with your @amzur.com credentials
          </p>
        </div>

        <form onSubmit={submit} className="space-y-3 rounded-2xl border border-white/10 bg-ink-850/80 p-5 backdrop-blur-xl">
          {mode === "register" && (
            <input
              type="text"
              placeholder="Full name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-ink-900/60 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-500/60 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
            />
          )}
          <input
            type="email"
            placeholder="Email (e.g. you@amzur.com)"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-ink-900/60 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-500/60 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
          />
          <input
            type="password"
            placeholder="Password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-ink-900/60 px-3 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-accent-500/60 focus:outline-none focus:ring-2 focus:ring-accent-500/20"
          />
          {error && (
            <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-br from-accent-500 to-fuchsia-500 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-accent-500/30 transition hover:brightness-110 disabled:opacity-50"
          >
            <KeyRound className="h-4 w-4" />
            {mode === "login" ? "Sign in" : "Create account"}
          </button>
        </form>

        <div className="flex flex-col items-center gap-3">
          <button
            onClick={() => setMode(mode === "login" ? "register" : "login")}
            className="text-sm text-slate-400 transition hover:text-white"
          >
            {mode === "login" ? "Need an account? Register" : "Already have an account? Sign in"}
          </button>

          <div className="flex items-center gap-3 text-xs text-slate-500">
            <div className="h-px w-10 bg-white/10" />
            or
            <div className="h-px w-10 bg-white/10" />
          </div>

          <a
            href={api.googleLoginUrl()}
            className="flex w-full max-w-sm items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 py-2.5 text-sm font-medium text-slate-100 transition hover:border-accent-500/40 hover:bg-white/10"
          >
            <svg className="h-4 w-4" viewBox="0 0 48 48">
              <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
              <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
              <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
              <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
            </svg>
            Continue with Google
          </a>
        </div>
      </div>
    </div>
  );
}
