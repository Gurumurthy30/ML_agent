import React from 'react';
import { Search, Compass, Code, Play, Scale, Check } from 'lucide-react';

const STAGES = [
  { id: 'data_explorer', label: 'Data Explorer', icon: Search },
  { id: 'planner', label: 'Planner', icon: Compass },
  { id: 'coder', label: 'Coder', icon: Code },
  { id: 'execute', label: 'Execute', icon: Play },
  { id: 'selector', label: 'Selector', icon: Scale },
];

export default function PipelineTracker({ activeNode, isRunning }) {
  const activeIndex = STAGES.findIndex((s) => s.id === activeNode);

  return (
    <div className="my-2 p-2.5 rounded-xl bg-[#201F1D] border border-border/80 shadow-sm select-none">
      <div className="flex items-center justify-between gap-1 overflow-x-auto terminal-scroll">
        {STAGES.map((stage, idx) => {
          const Icon = stage.icon;
          const isActive = isRunning && stage.id === activeNode;
          const isDone = activeIndex > -1 ? idx < activeIndex : false;

          let badgeClass = 'bg-[#181716] text-muted border-border/60';
          let iconColor = 'text-muted';
          let textColor = 'text-muted';

          if (isActive) {
            badgeClass = 'bg-accent/20 text-accent border-accent/60 ring-1 ring-accent/30 animate-pulse';
            iconColor = 'text-accent';
            textColor = 'text-primary font-medium';
          } else if (isDone) {
            badgeClass = 'bg-[#252422] text-[#868580] border-border/80';
            iconColor = 'text-success';
            textColor = 'text-[#C5C4C0]';
          }

          return (
            <React.Fragment key={stage.id}>
              <div
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-sans transition-all flex-shrink-0 ${badgeClass}`}
              >
                {isDone ? (
                  <Check className="w-3.5 h-3.5 text-success" />
                ) : (
                  <Icon className={`w-3.5 h-3.5 ${iconColor}`} />
                )}
                <span className={`text-[12px] tracking-tight ${textColor}`}>{stage.label}</span>
              </div>

              {idx < STAGES.length - 1 && (
                <div
                  className={`w-4 h-[1px] flex-shrink-0 transition-colors ${
                    activeIndex > idx ? 'bg-accent/60' : 'bg-border/60'
                  }`}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
