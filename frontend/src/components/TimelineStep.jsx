import StatusBadge from "./StatusBadge"
import { MissionControlGlyph } from "./MissionControlIcons"

const stepAccent = {
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
  blocked: "border-rose-200 bg-rose-100 text-rose-700",
  running: "border-violet-200 bg-violet-50 text-violet-700",
  pending: "border-slate-200 bg-slate-100 text-slate-600",
}

export default function TimelineStep({ step, isLast, active = false }) {
  const accent = stepAccent[step.status] || stepAccent.pending
  const emphasize = ["warning", "failed", "blocked"].includes(step.status)

  return (
    <div className="relative flex gap-4 pb-6 last:pb-0">
      {!isLast ? (
        <div className="absolute left-[1.18rem] top-12 h-[calc(100%-1.5rem)] w-px bg-gradient-to-b from-slate-300 via-slate-200 to-slate-100" />
      ) : null}
      <div
        className={`relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border text-sm font-semibold shadow-sm transition ${accent} ${
          active ? "ring-2 ring-indigo-400 ring-offset-2 ring-offset-white animate-pulse" : ""
        }`}
      >
        {step.step}
      </div>
      <div
        className={`flex-1 rounded-[24px] border px-5 py-4 transition-colors ${
          active
            ? "border-indigo-300 bg-indigo-50/60 shadow-[0_18px_45px_rgba(91,92,255,0.15)]"
            : emphasize
            ? "border-slate-200 bg-white shadow-[0_18px_45px_rgba(248,113,113,0.08)]"
            : "border-slate-100 bg-slate-50/70"
        }`}
      >
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h3 className="text-sm font-semibold text-slate-900">{step.stage}</h3>
              <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-500">{step.duration}</span>
              {active ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.16em] text-indigo-700">
                  <MissionControlGlyph name="running" className="h-3 w-3" />
                  Currently executing
                </span>
              ) : null}
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-500">{step.description}</p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={step.status} className="capitalize">
              {step.status}
            </StatusBadge>
            <div className={`hidden h-10 w-10 items-center justify-center rounded-2xl lg:flex ${accent}`}>
              <MissionControlGlyph name={step.status} className="h-5 w-5" />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
