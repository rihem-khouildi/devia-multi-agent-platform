import { MissionControlGlyph } from "./MissionControlIcons"

function CoverageRing({ value, required }) {
  const numeric = Number.parseFloat(String(value).replace("%", "")) || 0
  const requiredNumeric = Number.parseFloat(String(required).replace("%", "")) || 0
  const radius = 46
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (Math.min(numeric, 100) / 100) * circumference

  return (
    <div className="relative flex h-40 w-40 items-center justify-center">
      <svg viewBox="0 0 120 120" className="h-40 w-40 -rotate-90">
        <circle cx="60" cy="60" r={radius} stroke="#fee2e2" strokeWidth="10" fill="none" />
        <circle
          cx="60"
          cy="60"
          r={radius}
          stroke="url(#coverageGradient)"
          strokeWidth="10"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
        <defs>
          <linearGradient id="coverageGradient" x1="0" x2="1" y1="0" y2="1">
            <stop offset="0%" stopColor="#f97316" />
            <stop offset="100%" stopColor="#ef4444" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-2xl font-semibold text-slate-900">{value}</span>
        <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
          required {requiredNumeric}%
        </span>
      </div>
    </div>
  )
}

const STATUS_TONE = {
  passed: "text-emerald-600 bg-emerald-50",
  failed: "text-rose-600 bg-rose-50",
  warning: "text-amber-600 bg-amber-50",
  pending: "text-slate-500 bg-slate-100",
}

const STATUS_BADGE = {
  passed: "border-emerald-200 bg-emerald-50 text-emerald-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  pending: "border-slate-200 bg-slate-100 text-slate-600",
}

const FALLBACK_CHECKS = (runSummary) => [
  { key: "compile", label: "Compile", detail: "Passed", status: "passed", icon: "success" },
  { key: "tests", label: "Tests", detail: "Passed (18/18)", status: "passed", icon: "success" },
  {
    key: "coverage",
    label: "Coverage",
    detail: `${runSummary.coverage} · below ${runSummary.required}`,
    status: "warning",
    icon: "warning",
  },
  {
    key: "github_push",
    label: "GitHub Push",
    detail: "Blocked until quality gate passes",
    status: "failed",
    icon: "lock",
  },
]

export default function QualityShield({ runSummary, criteria }) {
  const items = criteria?.length ? criteria : FALLBACK_CHECKS(runSummary)
  return (
    <div className="rounded-[28px] border border-slate-200 bg-[linear-gradient(160deg,_#ffffff_0%,_#f8fafc_55%,_#fff7f7_100%)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)]">
      <div className="flex flex-col items-center gap-5 lg:flex-row lg:items-start">
        <div className="relative">
          <div className="absolute inset-0 -z-10 rounded-full bg-rose-100 blur-2xl" aria-hidden="true" />
          <div className="flex h-44 w-44 items-center justify-center rounded-full border border-rose-200 bg-white shadow-[0_25px_60px_rgba(244,63,94,0.18)]">
            <CoverageRing value={runSummary.coverage} required={runSummary.required} />
          </div>
          <div className="mt-3 flex justify-center">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-600 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] text-white">
              <MissionControlGlyph name="shield" className="h-3.5 w-3.5" />
              Quality Shield active
            </span>
          </div>
        </div>

        <div className="flex-1 space-y-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-rose-500">
              Quality Gate
            </div>
            <h3 className="mt-1 text-lg font-semibold tracking-tight text-slate-900">
              Devia protects the repository from incomplete validation.
            </h3>
          </div>

          <ul className="space-y-2">
            {items.map((check) => {
              const tone = STATUS_TONE[check.status] || STATUS_TONE.pending
              const badge = STATUS_BADGE[check.status] || STATUS_BADGE.pending
              return (
                <li
                  key={check.key || check.label}
                  className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-white/80 px-4 py-2.5 shadow-sm"
                >
                  <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${tone}`}>
                    <MissionControlGlyph name={check.icon} className="h-4 w-4" />
                  </span>
                  <div className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <span className="text-sm font-semibold text-slate-900">{check.label}</span>
                    {check.status ? (
                      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] ${badge}`}>
                        {check.status}
                      </span>
                    ) : null}
                    {check.detail ? (
                      <span className="basis-full break-words text-xs font-medium text-slate-500">
                        {check.detail}
                      </span>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </div>
  )
}
