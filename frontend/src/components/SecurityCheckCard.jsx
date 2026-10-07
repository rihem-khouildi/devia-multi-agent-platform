import { MissionControlGlyph } from "./MissionControlIcons"

const STATUS_TONE = {
  passed: {
    icon: "bg-emerald-50 text-emerald-600",
    chip: "border-emerald-200 bg-emerald-50 text-emerald-700",
    label: "Passed",
  },
  failed: {
    icon: "bg-rose-50 text-rose-600",
    chip: "border-rose-200 bg-rose-50 text-rose-700",
    label: "Failed",
  },
  warning: {
    icon: "bg-amber-50 text-amber-600",
    chip: "border-amber-200 bg-amber-50 text-amber-700",
    label: "Warning",
  },
  pending: {
    icon: "bg-slate-100 text-slate-500",
    chip: "border-slate-200 bg-slate-100 text-slate-600",
    label: "Pending",
  },
}

function formatTimestamp(value) {
  if (!value) return null
  try {
    const date = new Date(value)
    if (Number.isNaN(date.getTime())) return value
    return `${date.toUTCString().replace("GMT", "UTC")}`
  } catch (error) {
    return value
  }
}

export default function SecurityCheckCard({ data }) {
  if (!data) return null

  const overall = STATUS_TONE[data.status] || STATUS_TONE.pending
  const passed = data.criteria?.filter((c) => c.status === "passed").length || 0
  const total = data.criteria?.length || 0
  const scannedAt = formatTimestamp(data.scannedAt)

  return (
    <div className="space-y-5">
      <div className="rounded-[26px] border border-emerald-100 bg-[linear-gradient(160deg,_#ecfdf5_0%,_#ffffff_55%,_#eef2ff_100%)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-emerald-600 shadow-sm ring-1 ring-emerald-100">
              <MissionControlGlyph name="shield" className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-emerald-700">
                Security Sanity Check
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-slate-900">
                  {data.status === "passed"
                    ? "All security sanity checks passed"
                    : data.status === "warning"
                    ? "Security sanity checks raised warnings"
                    : data.status === "failed"
                    ? "Security sanity checks failed"
                    : "Security sanity checks pending"}
                </h3>
                <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] ${overall.chip}`}>
                  <MissionControlGlyph name={data.status === "passed" ? "success" : "warning"} className="h-3 w-3" />
                  {overall.label}
                </span>
                <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-[10.5px] font-semibold text-slate-600">
                  <span className="tabular-nums">{passed}</span>
                  <span className="opacity-70">/ {total} criteria</span>
                </span>
              </div>
            </div>
          </div>
          <div className="text-right">
            {scannedAt ? (
              <div className="text-[10.5px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                Scanned at
              </div>
            ) : null}
            <div className="font-mono text-[11.5px] text-slate-600">{scannedAt || "—"}</div>
            {data.scope ? (
              <div className="mt-1 text-[11px] text-slate-500">Scope: {data.scope}</div>
            ) : null}
          </div>
        </div>

        <p className="mt-3 max-w-3xl text-[13px] leading-6 text-slate-600">{data.description}</p>
      </div>

      <ul className="grid gap-3 md:grid-cols-2">
        {data.criteria.map((criterion) => {
          const tone = STATUS_TONE[criterion.status] || STATUS_TONE.pending
          return (
            <li
              key={criterion.key}
              className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-white p-3 shadow-sm"
            >
              <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${tone.icon}`}>
                <MissionControlGlyph name={criterion.icon} className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-sm font-semibold text-slate-900">{criterion.label}</h4>
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] ${tone.chip}`}>
                    {tone.label}
                  </span>
                </div>
                <p className="mt-1 text-[12.5px] leading-5 text-slate-600">{criterion.detail}</p>
              </div>
            </li>
          )
        })}
      </ul>

      {data.futureWork ? (
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/80 p-4">
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white text-indigo-600 ring-1 ring-indigo-100">
              <MissionControlGlyph name="sparkle" className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <div className="text-[10.5px] font-semibold uppercase tracking-[0.22em] text-indigo-600">
                Future work
              </div>
              <p className="mt-1 text-[12.5px] leading-5 text-slate-600">{data.futureWork}</p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
