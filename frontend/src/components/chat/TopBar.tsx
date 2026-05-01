import { ChevronDown } from "lucide-react";
import { AVAILABLE_MODELS, useSettingsStore } from "../../lib/settingsStore";

export default function TopBar() {
  const selectedModel = useSettingsStore((s) => s.selectedModel);
  const setSelectedModel = useSettingsStore((s) => s.setSelectedModel);

  const currentModel = AVAILABLE_MODELS.find((m) => m.id === selectedModel);

  return (
    <div className="flex items-center justify-end border-b border-white/5 bg-ink-900/60 px-6 py-3 backdrop-blur-xl">
      <div className="flex items-center gap-4">
        <div className="text-xs text-slate-500">Model:</div>
        <div className="group relative">
          <button className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm font-medium text-slate-100 transition hover:border-accent-500/50 hover:bg-white/10">
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-accent-400"></span>
              {currentModel?.label || "Select model"}
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
          </button>
          <div className="absolute right-0 top-full mt-1 hidden w-56 rounded-lg border border-white/10 bg-ink-950/90 shadow-xl backdrop-blur-xl group-hover:block">
            {AVAILABLE_MODELS.map((model) => (
              <button
                key={model.id}
                onClick={() => setSelectedModel(model.id)}
                className={
                  "w-full px-4 py-2.5 text-left text-sm transition " +
                  (selectedModel === model.id
                    ? "bg-accent-500/20 text-accent-300"
                    : "text-slate-300 hover:bg-white/5 hover:text-white")
                }
              >
                <div className="font-medium">{model.label}</div>
                <div className="text-xs text-slate-500">{model.provider}</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
