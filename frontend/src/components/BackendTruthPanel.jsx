import StatusBadge from "./StatusBadge"

const friendlyMap = {
  coverage_below_threshold: "Coverage below required threshold",
  manual_test_improvement_required: "Manual test improvement required",
  passed: "Passed",
  blocked: "Push blocked until quality gate passes",
  protected: "Repository protected",
  enabled: "Auto-retry enabled",
  disabled: "Auto-retry disabled",
}

const ROWS = [
  { key: "route", label: "route", tone: "warning" },
  { key: "next_action", label: "next_action", tone: "failed" },
  { key: "coverage", label: "coverage", tone: "warning" },
  { key: "required", label: "required", tone: null },
  { key: "compile_status", label: "compile", tone: "success" },
  { key: "test_status", label: "tests", tone: "success" },
  { key: "github_push", label: "github_push", tone: "blocked" },
  { key: "auto_coverage_retry", label: "auto_coverage_retry", tone: "failed" },
]

export default function BackendTruthPanel({ runSummary }) {
  return (
    <div className="space-y-3">
      <p className="text-xs leading-6 text-slate-500">
        Raw values returned by the backend orchestration layer. The frontend renders them as-is to prove every
        decision is traceable.
      </p>
      <div className="rounded-[24px] border border-slate-900/90 bg-[linear-gradient(180deg,_#0f172a_0%,_#111827_100%)] p-4 font-mono text-[12.5px] leading-6 text-slate-100 shadow-[0_25px_60px_rgba(15,23,42,0.25)]">
        <div className="mb-3 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.32em] text-slate-400">
          <span>backend.truth</span>
          <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-rose-300">live</span>
        </div>
        <div className="space-y-1.5">
          {ROWS.map((row) => {
            const value = runSummary[row.key] ?? "—"
            return (
              <div key={row.key} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="text-slate-400">{row.label}</span>
                <span className="text-slate-500">=</span>
                <span className="break-all font-semibold text-emerald-300">{value}</span>
              </div>
            )
          })}
        </div>
      </div>

      <ul className="grid gap-2 sm:grid-cols-2">
        {ROWS.map((row) => {
          const value = runSummary[row.key]
          const friendly = friendlyMap[value] || value
          return (
            <li
              key={`friendly-${row.key}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-100 bg-slate-50/80 px-3 py-2"
            >
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                {row.label}
              </span>
              {row.tone ? (
                <StatusBadge status={row.tone} size="sm" className="max-w-full">
                  {friendly}
                </StatusBadge>
              ) : (
                <span className="break-words text-xs font-semibold text-slate-700">{friendly}</span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
