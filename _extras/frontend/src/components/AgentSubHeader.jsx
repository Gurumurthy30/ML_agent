import React from 'react';

export default function AgentSubHeader({ agentName, agentColor = '#DA7756', badge, role }) {
  return (
    <div className="flex items-center gap-2 pt-3 pb-1 select-none">
      {/* Colored agent dot */}
      <span
        className="w-2.5 h-2.5 rounded-full flex-shrink-0 shadow-sm"
        style={{
          backgroundColor: agentColor,
          boxShadow: `0 0 8px ${agentColor}55`,
        }}
      />
      
      {/* Agent Name */}
      <span className="text-[13.5px] font-medium text-primary tracking-tight">
        {agentName}
      </span>

      {/* Role / Badge */}
      {badge && (
        <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-border/40 text-muted/90 border border-border/50">
          {badge}
        </span>
      )}

      {/* Subtle separator line */}
      <div className="flex-1 h-[1px] bg-border/40 ml-2" />
    </div>
  );
}
