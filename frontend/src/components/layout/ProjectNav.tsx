import {
  Activity,
  Database,
  Search,
  SlidersHorizontal,
  Trophy,
  CheckCircle2,
  FileText,
  History,
  Info,
} from "lucide-react";
import clsx from "clsx";
import { WorkspaceTab, useUIStore } from "../../store/uiStore";

interface NavItem {
  key: WorkspaceTab;
  label: string;
  icon: React.ElementType;
  badge?: string | number;
}

interface ProjectNavProps {
  runCount?: number;
  modelCount?: number;
  datasetCount?: number;
}

export function ProjectNav({ runCount, modelCount, datasetCount }: ProjectNavProps) {
  const { activeTab, setActiveTab } = useUIStore();

  const navItems: NavItem[] = [
    { key: "overview", label: "Overview", icon: Activity },
    { key: "dataset", label: "Dataset", icon: Database, badge: datasetCount },
    { key: "profile", label: "Profile", icon: Info },
    { key: "eda", label: "EDA Findings", icon: Search },
    { key: "features", label: "Features", icon: SlidersHorizontal },
    { key: "models", label: "Leaderboard", icon: Trophy, badge: modelCount },
    { key: "evaluation", label: "Evaluation", icon: CheckCircle2 },
    { key: "report", label: "Final Report", icon: FileText },
    { key: "runs", label: "Runs History", icon: History, badge: runCount },
  ];

  return (
    <aside className="w-56 flex-shrink-0 border-r border-slate-800 bg-[#090d16] flex flex-col justify-between select-none">
      <div className="p-3 space-y-1">
        <div className="px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-slate-500 font-semibold">
          Workspace
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.key;
          return (
            <button
              key={item.key}
              onClick={() => setActiveTab(item.key)}
              className={clsx(
                "w-full flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition",
                isActive
                  ? "bg-slate-800 text-sky-400 font-semibold"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
              )}
            >
              <div className="flex items-center gap-2.5">
                <Icon className={clsx("w-4 h-4", isActive ? "text-sky-400" : "text-slate-500")} />
                <span>{item.label}</span>
              </div>
              {item.badge !== undefined && item.badge !== null && (
                <span
                  className={clsx(
                    "text-[10px] px-1.5 py-0.5 rounded font-mono",
                    isActive ? "bg-sky-500/20 text-sky-300" : "bg-slate-800 text-slate-500"
                  )}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="p-3 border-t border-slate-800/60 text-xs text-slate-500 font-mono">
        <div className="text-[10px] text-slate-400 mb-1">Stack</div>
        <div className="text-[11px] text-slate-300">gpt-oss:120b</div>
        <div className="text-[10px] text-slate-500">Ollama Cloud / Scikit-learn</div>
      </div>
    </aside>
  );
}
