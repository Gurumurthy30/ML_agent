import React from "react";
import { cn as clsx } from "../../utils/cn";

interface BadgeProps {
  variant?: "success" | "running" | "warning" | "error" | "neutral" | "info" | "purple";
  children: React.ReactNode;
  className?: string;
  dot?: boolean;
}

export function Badge({ variant = "neutral", children, className, dot = false }: BadgeProps) {
  const variantStyles = {
    success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    running: "bg-sky-500/10 text-sky-400 border-sky-500/30 animate-pulse",
    warning: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    error: "bg-rose-500/10 text-rose-400 border-rose-500/30",
    neutral: "bg-slate-800 text-slate-300 border-slate-700",
    info: "bg-blue-500/10 text-blue-400 border-blue-500/30",
    purple: "bg-purple-500/10 text-purple-400 border-purple-500/30",
  };

  const dotColors = {
    success: "bg-emerald-400",
    running: "bg-sky-400 animate-ping",
    warning: "bg-amber-400",
    error: "bg-rose-400",
    neutral: "bg-slate-400",
    info: "bg-blue-400",
    purple: "bg-purple-400",
  };

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border tracking-wide",
        variantStyles[variant],
        className
      )}
    >
      {dot && <span className={clsx("w-1.5 h-1.5 rounded-full", dotColors[variant])} />}
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  switch (status.toUpperCase()) {
    case "SUCCESS":
    case "PASS":
    case "COMPLETED":
      return <Badge variant="success" dot>{status}</Badge>;
    case "RUNNING":
      return <Badge variant="running" dot>{status}</Badge>;
    case "NEEDS_INPUT":
    case "IMPROVE":
      return <Badge variant="warning" dot>{status}</Badge>;
    case "FAILED":
    case "ERROR":
    case "STOP":
      return <Badge variant="error" dot>{status}</Badge>;
    case "PENDING":
    default:
      return <Badge variant="neutral" dot>{status}</Badge>;
  }
}
