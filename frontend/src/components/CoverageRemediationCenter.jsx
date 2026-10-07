import { MissionControlGlyph } from "./MissionControlIcons"

function CoverageBar({ current, required }) {
  const max = Math.max(required, current, 100)
  const currentPct = (current / max) * 100
  const requiredPct = (required / max) * 100
  return (
    <div className="space-y-2">
      <div className="relative h-3 overflow-hidden rounded-full bg-slate-100">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-[linear-gradient(90deg,_#f97316_0%,_#ef4444_100%)]"
          style={{ width: `${currentPct}%` }}
        />
        <div
          className="absolute inset-y-0 w-px bg-slate-700/70"
          style={{ left: `${requiredPct}%` }}
          aria-hidden="true"
        />
      </div>
      <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500">
        <span className="text-rose-600 tabular-nums">Current {current}%</span>
        <span className="tabular-nums">Required {required}%</span>
      </div>
    </div>
  )
}

function MetricTile({ label, value, tone = "slate", helper }) {
  const toneClass = {
    rose: "border-rose-200 bg-rose-50 text-rose-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    slate: "border-slate-200 bg-slate-50 text-slate-700",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
  }[tone]
  return (
    <div className={`rounded-2xl border p-3 ${toneClass}`}>
      <div className="text-[10.5px] font-semibold uppercase tracking-[0.18em] opacity-80">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value}</div>
      {helper ? <div className="mt-1 text-[11px] font-medium opacity-80">{helper}</div> : null}
    </div>
  )
}

export default function CoverageRemediationCenter({
  remediation,
  runSummary,
  coverageGap,
  onViewGap,
  onGeneratePlan,
  onExportReport,
}) {
  if (!remediation || !coverageGap) return null

  return (
    <div className="space-y-5">
      <div className="rounded-[26px] border border-rose-100 bg-[linear-gradient(160deg,_#fff1f2_0%,_#ffffff_55%,_#eef2ff_100%)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-rose-600 shadow-sm ring-1 ring-rose-100">
              <MissionControlGlyph name="warning" className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-rose-700">
                Detected issue
              </div>
              <h3 className="mt-1 text-base font-semibold text-slate-900">{remediation.detectedIssue}</h3>
              <p className="mt-1 max-w-3xl text-[13px] leading-6 text-slate-600">{remediation.whyItMatters}</p>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-200 bg-white px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700">
            <MissionControlGlyph name="lock" className="h-3.5 w-3.5" />
            route = {runSummary.route}
          </span>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <MetricTile label="Current coverage" value={`${coverageGap.current}%`} tone="rose" helper={`measured by ${coverageGap.measuredBy}`} />
          <MetricTile label="Required coverage" value={`${coverageGap.required}%`} tone="slate" helper="quality gate threshold" />
          <MetricTile label="Coverage gap" value={`${coverageGap.gap}%`} tone="amber" helper={`branch coverage ${coverageGap.branchCoverage}%`} />
        </div>

        <div className="mt-4">
          <CoverageBar current={coverageGap.current} required={coverageGap.required} />
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
        <section className="rounded-[24px] border border-slate-100 bg-white p-4 shadow-sm">
          <header className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                <MissionControlGlyph name="brain" className="h-3.5 w-3.5" />
              </span>
              <h4 className="text-sm font-semibold text-slate-900">Root cause</h4>
            </div>
          </header>
          <p className="text-[13px] leading-6 text-slate-600">{remediation.rootCause}</p>

          <div className="mt-4 rounded-2xl border border-rose-100 bg-rose-50/70 p-3">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.22em] text-rose-700">
              Safety rule
            </div>
            <p className="mt-1 text-[12.5px] leading-5 text-rose-800">{remediation.safetyRule}</p>
          </div>

          <div className="mt-3 rounded-2xl border border-indigo-100 bg-indigo-50/70 p-3">
            <div className="text-[10.5px] font-semibold uppercase tracking-[0.22em] text-indigo-700">
              Suggested next action
            </div>
            <p className="mt-1 text-[12.5px] leading-5 text-indigo-900">{remediation.suggestedNextAction}</p>
          </div>
        </section>

        <section className="rounded-[24px] border border-slate-100 bg-white p-4 shadow-sm">
          <header className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-rose-50 text-rose-600">
                <MissionControlGlyph name="target" className="h-3.5 w-3.5" />
              </span>
              <h4 className="text-sm font-semibold text-slate-900">Recommended missing tests</h4>
            </div>
            <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {remediation.missingAreas.length}
            </span>
          </header>
          <ul className="space-y-2">
            {remediation.missingAreas.map((area) => (
              <li
                key={area.key}
                className="flex items-start gap-2.5 rounded-2xl border border-slate-100 bg-slate-50/70 px-3 py-2"
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-rose-600 ring-1 ring-rose-100">
                  <MissionControlGlyph name={area.icon} className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0">
                  <div className="text-[13px] font-semibold text-slate-900">{area.title}</div>
                  <p className="mt-0.5 text-[12px] leading-5 text-slate-600">{area.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-[22px] border border-slate-200 bg-[linear-gradient(160deg,_#f8fafc_0%,_#ffffff_70%)] px-4 py-3">
        <div className="mr-auto flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-600">
          <MissionControlGlyph name="sparkle" className="h-3.5 w-3.5" />
          Operator actions
        </div>
        {onViewGap ? (
          <button
            type="button"
            onClick={onViewGap}
            className="inline-flex items-center gap-1.5 rounded-2xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-900"
          >
            <MissionControlGlyph name="graph" className="h-3.5 w-3.5" />
            View Coverage Gap
          </button>
        ) : null}
        {onGeneratePlan ? (
          <button
            type="button"
            onClick={onGeneratePlan}
            className="inline-flex items-center gap-1.5 rounded-2xl border border-indigo-200 bg-indigo-50 px-3.5 py-2 text-xs font-semibold text-indigo-700 shadow-sm transition hover:bg-indigo-100"
          >
            <MissionControlGlyph name="brain" className="h-3.5 w-3.5" />
            Generate Test Improvement Plan
          </button>
        ) : null}
        {onExportReport ? (
          <button
            type="button"
            onClick={onExportReport}
            className="inline-flex items-center gap-1.5 rounded-2xl bg-slate-900 px-3.5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-slate-800"
          >
            <MissionControlGlyph name="file" className="h-3.5 w-3.5" />
            Export Coverage Report
          </button>
        ) : null}
      </div>
    </div>
  )
}
