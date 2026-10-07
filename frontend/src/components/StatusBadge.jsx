import { MissionControlGlyph } from "./MissionControlIcons"

const statusClasses = {
  info: "border-sky-200 bg-sky-50 text-sky-700",
  pending: "border-slate-200 bg-slate-100 text-slate-600",
  running: "border-violet-200 bg-violet-50 text-violet-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
  blocked: "border-rose-200 bg-rose-100 text-rose-700",
}

const iconNames = {
  info: "graph",
  pending: "pending",
  running: "running",
  success: "success",
  warning: "warning",
  failed: "failed",
  blocked: "blocked",
}

export default function StatusBadge({ status, children, size = "md", className = "" }) {
  const normalized = String(status || "info").toLowerCase()
  const tone = statusClasses[normalized] || statusClasses.info
  const compact = size === "sm"

  return (
    <span
      className={`inline-flex max-w-full items-start gap-1.5 rounded-full border font-medium whitespace-normal break-words ${tone} ${compact ? "px-2.5 py-1 text-[11px]" : "px-3 py-1.5 text-xs"} ${className}`}
    >
      <MissionControlGlyph name={iconNames[normalized] || "graph"} className={`${compact ? "h-3.5 w-3.5" : "h-4 w-4"} mt-0.5 shrink-0`} />
      <span className="min-w-0 whitespace-normal break-words">{children || status}</span>
    </span>
  )
}
