import { useState } from "react"
import { MissionControlGlyph } from "./MissionControlIcons"

const TONE = {
  sky: {
    chip: "border-sky-200 bg-sky-50 text-sky-700",
    icon: "bg-sky-50 text-sky-600",
    accent: "from-sky-200 via-sky-100 to-transparent",
  },
  violet: {
    chip: "border-violet-200 bg-violet-50 text-violet-700",
    icon: "bg-violet-50 text-violet-600",
    accent: "from-violet-200 via-violet-100 to-transparent",
  },
  indigo: {
    chip: "border-indigo-200 bg-indigo-50 text-indigo-700",
    icon: "bg-indigo-50 text-indigo-600",
    accent: "from-indigo-200 via-indigo-100 to-transparent",
  },
  emerald: {
    chip: "border-emerald-200 bg-emerald-50 text-emerald-700",
    icon: "bg-emerald-50 text-emerald-600",
    accent: "from-emerald-200 via-emerald-100 to-transparent",
  },
  amber: {
    chip: "border-amber-200 bg-amber-50 text-amber-700",
    icon: "bg-amber-50 text-amber-600",
    accent: "from-amber-200 via-amber-100 to-transparent",
  },
  rose: {
    chip: "border-rose-200 bg-rose-50 text-rose-700",
    icon: "bg-rose-50 text-rose-600",
    accent: "from-rose-200 via-rose-100 to-transparent",
  },
}

function riskTone(risk = "") {
  const lower = risk.toLowerCase()
  if (lower.startsWith("high")) return "border-rose-200 bg-rose-50 text-rose-700"
  if (lower.startsWith("medium")) return "border-amber-200 bg-amber-50 text-amber-700"
  if (lower.startsWith("low")) return "border-emerald-200 bg-emerald-50 text-emerald-700"
  return "border-slate-200 bg-slate-50 text-slate-600"
}

function ConfidenceBar({ value }) {
  const pct = Math.max(0, Math.min(1, Number(value) || 0)) * 100
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-[linear-gradient(90deg,_#5B5CFF_0%,_#00AEEF_100%)]"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[11px] font-semibold tabular-nums text-slate-600">{Math.round(pct)}%</span>
    </div>
  )
}

function JournalEntry({ entry, index, isLast, isOpen, onToggle }) {
  const tone = TONE[entry.tone] || TONE.indigo
  const evidenceCount = entry.evidence?.length || 0

  return (
    <li className="relative pl-12">
      {!isLast ? (
        <div
          className={`absolute left-[1.18rem] top-12 h-[calc(100%-1.5rem)] w-px bg-gradient-to-b ${tone.accent}`}
          aria-hidden="true"
        />
      ) : null}

      <div
        className={`absolute left-0 top-3 flex h-10 w-10 items-center justify-center rounded-2xl border border-white shadow-[0_8px_22px_rgba(15,23,42,0.08)] ${tone.icon}`}
      >
        <MissionControlGlyph name={entry.icon} className="h-5 w-5" />
      </div>

      <div className="rounded-[24px] border border-slate-100 bg-white p-4 shadow-sm transition hover:shadow-[0_18px_45px_rgba(15,23,42,0.07)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-[0.18em] ${tone.chip}`}>
                <span className="tabular-nums">#{String(index + 1).padStart(2, "0")}</span>
                <span>· {entry.agent}</span>
              </span>
              <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10.5px] font-semibold ${riskTone(entry.risk)}`}>
                <MissionControlGlyph name="warning" className="h-3 w-3" />
                Risk: {entry.risk?.split(" — ")[0] || "Unknown"}
              </span>
            </div>
            <h3 className="mt-2 text-[15px] font-semibold leading-snug text-slate-900">
              {entry.decision}
            </h3>
            <p className="mt-1 text-[12.5px] leading-5 text-slate-600">{entry.reason}</p>
          </div>

          <div className="flex flex-col items-end gap-2">
            <ConfidenceBar value={entry.confidence} />
            <button
              type="button"
              onClick={onToggle}
              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10.5px] font-semibold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50"
              aria-expanded={isOpen}
            >
              <MissionControlGlyph name={isOpen ? "blocked" : "help"} className="h-3 w-3" />
              {isOpen ? "Hide" : `Evidence (${evidenceCount})`}
            </button>
          </div>
        </div>

        {isOpen ? (
          <div className="mt-4 grid gap-3 rounded-2xl border border-slate-100 bg-slate-50/70 p-3 lg:grid-cols-2">
            <section>
              <div className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                <MissionControlGlyph name="target" className="h-3 w-3" />
                Evidence used
              </div>
              {evidenceCount ? (
                <ul className="space-y-1.5">
                  {entry.evidence.map((line, idx) => (
                    <li
                      key={`${entry.key}-evidence-${idx}`}
                      className="flex items-start gap-2 rounded-xl border border-slate-100 bg-white px-2.5 py-1.5 text-[12px] leading-5 text-slate-600"
                    >
                      <MissionControlGlyph name="success" className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
                      <span className="min-w-0 break-words">{line}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rounded-xl border border-dashed border-slate-200 bg-white px-2.5 py-1.5 text-[11.5px] italic text-slate-500">
                  No evidence captured.
                </p>
              )}
            </section>

            <section className="space-y-3">
              <div>
                <div className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                  <MissionControlGlyph name="warning" className="h-3 w-3" />
                  Risk detected
                </div>
                <div className={`rounded-xl border px-3 py-2 text-[12px] leading-5 ${riskTone(entry.risk)}`}>
                  {entry.risk || "No risk recorded."}
                </div>
              </div>

              <div>
                <div className="mb-1.5 flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                  <MissionControlGlyph name="file" className="h-3 w-3" />
                  Produced artifact
                </div>
                <div className="inline-flex max-w-full items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 font-mono text-[11.5px] text-slate-700">
                  <MissionControlGlyph name="file" className="h-3 w-3 text-slate-500" />
                  <span className="truncate">{entry.artifact || "—"}</span>
                </div>
              </div>
            </section>
          </div>
        ) : null}
      </div>
    </li>
  )
}

export default function AiDecisionJournal({ entries }) {
  const [openKey, setOpenKey] = useState(entries?.[entries.length - 1]?.key || null)

  if (!entries?.length) {
    return (
      <p className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-sm italic text-slate-500">
        No agent decisions captured for this run yet.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-[22px] border border-indigo-100 bg-[linear-gradient(160deg,_#eef2ff_0%,_#ffffff_70%)] px-4 py-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-indigo-700">
          <MissionControlGlyph name="brain" className="h-3.5 w-3.5" />
          Agents explain themselves
        </div>
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> Low risk
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-amber-500" /> Medium risk
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-rose-500" /> High risk
          </span>
        </div>
      </div>

      <ol className="relative space-y-4">
        {entries.map((entry, index) => (
          <JournalEntry
            key={entry.key}
            entry={entry}
            index={index}
            isLast={index === entries.length - 1}
            isOpen={openKey === entry.key}
            onToggle={() => setOpenKey((current) => (current === entry.key ? null : entry.key))}
          />
        ))}
      </ol>
    </div>
  )
}
