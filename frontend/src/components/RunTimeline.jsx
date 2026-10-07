import { JURY_PIPELINE_STEPS, normalizePipelineStatus } from "../lib/pipelineSteps"

const STATUS_CFG = {
  running: {
    dot: "border-sky-300 bg-sky-50",
    dotInner: "bg-sky-500 animate-pulse",
    badge: "border-sky-200 bg-sky-50 text-sky-700",
    label: "text-slate-900",
    line: "bg-sky-200",
  },
  success: {
    dot: "border-emerald-300 bg-emerald-50",
    dotInner: "bg-emerald-500",
    badge: "border-emerald-200 bg-emerald-50 text-emerald-700",
    label: "text-slate-900",
    line: "bg-emerald-200",
  },
  failed: {
    dot: "border-rose-300 bg-rose-50",
    dotInner: "bg-rose-500",
    badge: "border-rose-200 bg-rose-50 text-rose-700",
    label: "text-slate-900",
    line: "bg-rose-200",
  },
  skipped: {
    dot: "border-slate-300 bg-slate-50",
    dotInner: "bg-slate-400",
    badge: "border-slate-200 bg-slate-50 text-slate-500",
    label: "text-slate-700",
    line: "bg-slate-200",
  },
  pending: {
    dot: "border-slate-300 bg-white",
    dotInner: "bg-slate-300",
    badge: "border-slate-200 bg-white text-slate-500",
    label: "text-slate-700",
    line: "bg-slate-200",
  },
}

function deriveStepStates(events) {
  const byStep = {}

  for (const event of events) {
    byStep[event.step] = {
      key: event.step,
      label: JURY_PIPELINE_STEPS.find((step) => step.key === event.step)?.label || event.step,
      status: normalizePipelineStatus(event.status),
      message: event.message,
      details: event.details,
      created_at: event.created_at,
    }
  }

  return JURY_PIPELINE_STEPS.map((step) => byStep[step.key] || { ...step, status: "pending" })
}

function formatTime(value) {
  if (!value) return null
  try {
    return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
  } catch {
    return null
  }
}

export default function RunTimeline({ events = [], steps }) {
  const items = steps || deriveStepStates(events)

  return (
    <ol className="relative space-y-0">
      {items.map((step, index) => {
        const status = step.status || "pending"
        const cfg = STATUS_CFG[status] || STATUS_CFG.pending
        const isLast = index === items.length - 1
        const time = formatTime(step.created_at)

        return (
          <li key={step.key} className="relative flex gap-4">
            {!isLast ? (
              <div className={`absolute left-[13px] top-[28px] h-full w-px ${cfg.line}`} aria-hidden="true" />
            ) : null}

            <div className="relative z-10 mt-1 shrink-0">
              <div className={`flex h-7 w-7 items-center justify-center rounded-full border-2 ${cfg.dot}`}>
                <span className={`h-2.5 w-2.5 rounded-full ${cfg.dotInner}`} />
              </div>
            </div>

            <div className="min-w-0 flex-1 pb-6">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`text-sm font-medium ${cfg.label}`}>{step.label}</span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${cfg.badge}`}>
                  {status}
                </span>
                {time ? <span className="text-[11px] text-slate-500">{time}</span> : null}
              </div>

              {step.message ? (
                <p className="mt-1 text-xs leading-relaxed text-slate-500 break-words">
                  {step.message}
                </p>
              ) : null}

              {step.details && Object.keys(step.details).length > 0 ? (
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
                  {Object.entries(step.details).map(([key, value]) => {
                    if (value == null || Array.isArray(value) || typeof value === "object") return null
                    return (
                      <span key={key} className="text-[11px] text-slate-500">
                        {key}: <span className="text-slate-700">{String(value)}</span>
                      </span>
                    )
                  })}
                </div>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
