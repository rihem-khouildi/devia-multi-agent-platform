import { MissionControlGlyph } from "./MissionControlIcons"

function impactTone(impact) {
  if (impact === "high") return "border-rose-200 bg-rose-50 text-rose-700"
  if (impact === "medium") return "border-amber-200 bg-amber-50 text-amber-700"
  if (impact === "low") return "border-emerald-200 bg-emerald-50 text-emerald-700"
  return "border-slate-200 bg-slate-50 text-slate-600"
}

function typeTone(type) {
  const lower = String(type || "").toLowerCase()
  if (lower === "unit") return "border-emerald-200 bg-emerald-50 text-emerald-700"
  if (lower === "mockmvc") return "border-indigo-200 bg-indigo-50 text-indigo-700"
  if (lower === "integration") return "border-violet-200 bg-violet-50 text-violet-700"
  return "border-slate-200 bg-slate-50 text-slate-600"
}

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
          aria-label="required threshold"
        />
      </div>
      <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500">
        <span className="text-rose-600 tabular-nums">Current {current}%</span>
        <span className="tabular-nums">Required {required}%</span>
      </div>
    </div>
  )
}

function MissingAreaCard({ area }) {
  return (
    <li className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-white p-3 shadow-sm">
      <span className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${impactTone(area.impact)}`}>
        <MissionControlGlyph name={area.icon} className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="text-sm font-semibold text-slate-900">{area.title}</h4>
          <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.16em] ${impactTone(area.impact)}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
            {area.impact} impact
          </span>
        </div>
        <p className="mt-1 text-[12.5px] leading-5 text-slate-600">{area.detail}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px]">
          <span className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-0.5 font-mono text-slate-600">
            <MissionControlGlyph name="file" className="h-3 w-3 text-slate-500" />
            {area.target}
          </span>
          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700">
            <MissionControlGlyph name="success" className="h-3 w-3" />
            +{area.estimatedUplift}% if covered
          </span>
        </div>
      </div>
    </li>
  )
}

function RecommendedTestRow({ test }) {
  return (
    <li className="rounded-2xl border border-slate-100 bg-white p-3 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2 py-0.5 font-mono text-[11.5px] text-slate-700">
            {test.name}
          </span>
          <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.16em] ${typeTone(test.type)}`}>
            {test.type}
          </span>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
          <MissionControlGlyph name="success" className="h-3 w-3" />
          +{test.gain}% coverage
        </span>
      </div>
      <p className="mt-2 text-[12.5px] leading-5 text-slate-600">{test.detail}</p>
      <div className="mt-2 inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-0.5 font-mono text-[11px] text-slate-600">
        <MissionControlGlyph name="file" className="h-3 w-3 text-slate-500" />
        {test.target}
      </div>
    </li>
  )
}

export default function CoverageGapExplorer({ data }) {
  if (!data) return null

  const totalUplift = data.recommendedTests.reduce((acc, test) => acc + (test.gain || 0), 0)
  const wouldClear = data.current + totalUplift >= data.required

  return (
    <div className="space-y-5">
      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-[24px] border border-rose-100 bg-[linear-gradient(160deg,_#fff1f2_0%,_#ffffff_70%)] p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-rose-500">
                Coverage gap
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-3xl font-semibold tracking-tight text-rose-600 tabular-nums">
                  -{data.gap}%
                </span>
                <span className="text-xs font-medium text-slate-500">
                  below the {data.required}% gate
                </span>
              </div>
              <p className="mt-2 max-w-md text-xs leading-5 text-slate-500">
                Measured by {data.measuredBy} on {data.scope}. Branch coverage sits at{" "}
                <span className="font-semibold text-slate-700">{data.branchCoverage}%</span>{" "}
                vs. required <span className="font-semibold text-slate-700">{data.branchRequired}%</span>.
              </p>
            </div>
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-100 text-rose-600">
              <MissionControlGlyph name="warning" className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-4">
            <CoverageBar current={data.current} required={data.required} />
          </div>
        </div>

        <div className="rounded-[24px] border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-indigo-600">
                If the recommended tests are added
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-3xl font-semibold tracking-tight text-indigo-700 tabular-nums">
                  +{totalUplift.toFixed(1)}%
                </span>
                <span className="text-xs font-medium text-slate-500">estimated uplift</span>
              </div>
              <p className="mt-2 max-w-md text-xs leading-5 text-slate-500">
                Projected coverage would land near{" "}
                <span className="font-semibold text-slate-900 tabular-nums">
                  {Math.min(100, data.current + totalUplift).toFixed(1)}%
                </span>
                .
              </p>
            </div>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] ${
                wouldClear
                  ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                  : "border-amber-200 bg-amber-50 text-amber-700"
              }`}
            >
              <MissionControlGlyph name={wouldClear ? "success" : "warning"} className="h-3.5 w-3.5" />
              {wouldClear ? "Quality gate cleared" : "Still under threshold"}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <section>
          <header className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-rose-50 text-rose-600">
                <MissionControlGlyph name="target" className="h-3.5 w-3.5" />
              </span>
              <h3 className="text-sm font-semibold text-slate-900">Likely missing test areas</h3>
            </div>
            <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {data.missingAreas.length}
            </span>
          </header>
          <ul className="space-y-2">
            {data.missingAreas.map((area) => (
              <MissingAreaCard key={area.key} area={area} />
            ))}
          </ul>
        </section>

        <section>
          <header className="mb-3 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
                <MissionControlGlyph name="launch" className="h-3.5 w-3.5" />
              </span>
              <h3 className="text-sm font-semibold text-slate-900">Recommended tests to add</h3>
            </div>
            <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {data.recommendedTests.length}
            </span>
          </header>
          <ul className="space-y-2">
            {data.recommendedTests.map((test) => (
              <RecommendedTestRow key={test.key} test={test} />
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}
