import { MissionControlGlyph } from "./MissionControlIcons"

const TONE = {
  sky: {
    border: "border-sky-200",
    iconShell: "bg-sky-50 text-sky-600",
    chip: "border-sky-200 bg-sky-50 text-sky-700",
    arrow: "from-sky-300 via-sky-200 to-transparent",
    rail: "bg-sky-200",
  },
  indigo: {
    border: "border-indigo-200",
    iconShell: "bg-indigo-50 text-indigo-600",
    chip: "border-indigo-200 bg-indigo-50 text-indigo-700",
    arrow: "from-indigo-300 via-indigo-200 to-transparent",
    rail: "bg-indigo-200",
  },
  violet: {
    border: "border-violet-200",
    iconShell: "bg-violet-50 text-violet-600",
    chip: "border-violet-200 bg-violet-50 text-violet-700",
    arrow: "from-violet-300 via-violet-200 to-transparent",
    rail: "bg-violet-200",
  },
  emerald: {
    border: "border-emerald-200",
    iconShell: "bg-emerald-50 text-emerald-600",
    chip: "border-emerald-200 bg-emerald-50 text-emerald-700",
    arrow: "from-emerald-300 via-emerald-200 to-transparent",
    rail: "bg-emerald-200",
  },
  amber: {
    border: "border-amber-200",
    iconShell: "bg-amber-50 text-amber-600",
    chip: "border-amber-200 bg-amber-50 text-amber-700",
    arrow: "from-amber-300 via-amber-200 to-transparent",
    rail: "bg-amber-200",
  },
  rose: {
    border: "border-rose-200",
    iconShell: "bg-rose-50 text-rose-600",
    chip: "border-rose-200 bg-rose-50 text-rose-700",
    arrow: "from-rose-300 via-rose-200 to-transparent",
    rail: "bg-rose-200",
  },
}

function AgentNode({ entry, tone }) {
  return (
    <div className={`flex h-full flex-col rounded-[22px] border bg-white p-4 shadow-sm ${tone.border}`}>
      <div className="flex items-center gap-3">
        <span className={`flex h-10 w-10 items-center justify-center rounded-2xl ${tone.iconShell}`}>
          <MissionControlGlyph name={entry.icon} className="h-5 w-5" />
        </span>
        <div className="min-w-0">
          <div className="text-[10.5px] font-semibold uppercase tracking-[0.22em] text-slate-400">Agent</div>
          <div className="truncate text-sm font-semibold text-slate-900">{entry.agent}</div>
        </div>
      </div>
      <p className="mt-3 text-[12.5px] leading-5 text-slate-600">{entry.role}</p>
    </div>
  )
}

function ArtifactNode({ entry, tone }) {
  return (
    <div className={`flex h-full flex-col rounded-[22px] border bg-[linear-gradient(180deg,_#ffffff_0%,_#f8fafc_100%)] p-4 shadow-sm ${tone.border}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10.5px] font-semibold uppercase tracking-[0.22em] text-slate-400">Produces</div>
          <div className="truncate text-sm font-semibold text-slate-900">{entry.artifactName}</div>
        </div>
        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${tone.chip}`}>
          <MissionControlGlyph name="file" className="h-3 w-3" />
          {entry.artifactType}
        </span>
      </div>
      <p className="mt-2 text-[12.5px] leading-5 text-slate-600">{entry.summary}</p>
      <div className="mt-3 inline-flex max-w-full items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-0.5 font-mono text-[11px] text-slate-600">
        <MissionControlGlyph name="file" className="h-3 w-3 text-slate-500" />
        <span className="truncate">{entry.artifactFile}</span>
      </div>
      {entry.metrics?.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {entry.metrics.map((metric) => (
            <span
              key={metric}
              className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600"
            >
              {metric}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function HandoffArrow({ tone, label }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 px-1 py-2 lg:flex-row lg:py-0">
      <div className={`h-1.5 w-12 rounded-full bg-gradient-to-r ${tone.arrow} lg:w-full`} />
      <div className={`flex h-9 w-9 items-center justify-center rounded-full border ${tone.border} bg-white shadow-sm`}>
        <MissionControlGlyph name="arrow" className="h-4 w-4 text-slate-500 rotate-90 lg:rotate-0" />
      </div>
      <div className={`h-1.5 w-12 rounded-full bg-gradient-to-r ${tone.arrow} lg:w-full`} />
      {label ? (
        <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
          {label}
        </span>
      ) : null}
    </div>
  )
}

export default function AgentArtifactMap({ entries }) {
  if (!entries?.length) return null

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[22px] border border-slate-200 bg-[linear-gradient(160deg,_#f8fafc_0%,_#ffffff_70%)] px-4 py-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-600">
          <MissionControlGlyph name="graph" className="h-3.5 w-3.5" />
          Agent → Artifact handoff
        </div>
        <p className="text-[11px] text-slate-500">
          Every agent produces exactly one artifact. The artifact is the handoff contract for the next agent.
        </p>
      </div>

      <ol className="space-y-4">
        {entries.map((entry, index) => {
          const tone = TONE[entry.tone] || TONE.indigo
          const isLast = index === entries.length - 1
          return (
            <li key={entry.key} className="relative">
              <div className="grid items-stretch gap-3 lg:grid-cols-[minmax(0,0.9fr)_auto_minmax(0,1.6fr)]">
                <AgentNode entry={entry} tone={tone} />
                <HandoffArrow tone={tone} label="produces" />
                <ArtifactNode entry={entry} tone={tone} />
              </div>

              {!isLast ? (
                <div className="flex items-center gap-2 pl-2 pt-2">
                  <span className={`flex h-6 w-6 items-center justify-center rounded-full border bg-white shadow-sm ${tone.border}`}>
                    <MissionControlGlyph name="arrow" className="h-3 w-3 rotate-90 text-slate-500" />
                  </span>
                  <div className="flex-1 border-t border-dashed border-slate-200" />
                  <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                    consumed by {entry.consumedBy}
                  </span>
                </div>
              ) : (
                <div className="flex items-center gap-2 pl-2 pt-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full border border-slate-900 bg-slate-900 text-white shadow-sm">
                    <MissionControlGlyph name="lock" className="h-3 w-3" />
                  </span>
                  <div className="flex-1 border-t border-dashed border-slate-300" />
                  <span className="rounded-full border border-slate-900 bg-slate-900 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-white">
                    final artifact
                  </span>
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
