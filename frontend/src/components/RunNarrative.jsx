import { MissionControlGlyph } from "./MissionControlIcons"

const highlightTone = {
  Story: "bg-sky-50 text-sky-700 border-sky-100",
  Context: "bg-violet-50 text-violet-700 border-violet-100",
  Code: "bg-indigo-50 text-indigo-700 border-indigo-100",
  Tests: "bg-emerald-50 text-emerald-700 border-emerald-100",
  Coverage: "bg-amber-50 text-amber-700 border-amber-100",
  Decision: "bg-rose-50 text-rose-700 border-rose-100",
}

export default function RunNarrative({ steps, runSummary }) {
  return (
    <div className="space-y-5">
      <div className="rounded-[28px] border border-slate-200/70 bg-[linear-gradient(160deg,_#ffffff_0%,_#f8fafc_55%,_#eef2ff_100%)] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)]">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-indigo-600">
          <MissionControlGlyph name="sparkle" className="h-3.5 w-3.5" />
          Run Narrative
        </div>
        <p className="mt-3 text-base leading-7 text-slate-700">
          Devia loaded the Jira story <span className="font-semibold text-slate-900">{runSummary.story_id}</span>, injected
          GraphRAG project context, generated Spring Boot artifacts, compiled successfully, and executed tests. However,
          JaCoCo coverage reached only <span className="font-semibold text-rose-600">{runSummary.coverage}</span> while the
          required threshold is <span className="font-semibold text-slate-900">{runSummary.required}</span>. The Quality
          Gate blocked the GitHub push to protect the repository.
        </p>
      </div>

      <ol className="space-y-3">
        {steps.map((entry, index) => {
          const tone = highlightTone[entry.highlight] || "bg-slate-50 text-slate-700 border-slate-100"
          return (
            <li
              key={entry.highlight}
              className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-white px-4 py-3 shadow-sm"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-xs font-semibold text-slate-500">
                {index + 1}
              </div>
              <div className="min-w-0 flex-1">
                <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${tone}`}>
                  {entry.highlight}
                </span>
                <p className="mt-2 text-sm leading-6 text-slate-600">{entry.text}</p>
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
