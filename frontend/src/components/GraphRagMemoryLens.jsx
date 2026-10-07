import { MissionControlGlyph } from "./MissionControlIcons"

export default function GraphRagMemoryLens({ graphRag }) {
  return (
    <div className="space-y-5">
      <div className="rounded-[26px] border border-violet-100 bg-[linear-gradient(160deg,_#f5f3ff_0%,_#eef2ff_55%,_#ffffff_100%)] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-violet-100 text-violet-600">
              <MissionControlGlyph name="brain" className="h-5 w-5" />
            </div>
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-violet-600">
                Project Memory Injected
              </div>
              <div className="text-sm font-semibold text-slate-900">
                {graphRag.boundedContext} · {graphRag.domain}
              </div>
            </div>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-white px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">
            <MissionControlGlyph name="success" className="h-3.5 w-3.5" />
            Context ready · {graphRag.confidence}
          </span>
        </div>

        <p className="mt-4 text-xs leading-6 text-slate-600">
          GraphRAG acts like project memory. It retrieved relevant entities, business rules, and impacted files
          before a single line of code was written, so the autonomous agents stay inside the right bounded context.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Related Entities</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {graphRag.relatedEntities.map((entity) => (
              <span
                key={entity}
                className="inline-flex items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs font-medium text-sky-700"
              >
                <MissionControlGlyph name="graph" className="h-3.5 w-3.5" />
                {entity}
              </span>
            ))}
          </div>

          <div className="mt-5 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Business Rules</div>
          <ul className="mt-3 space-y-2">
            {graphRag.businessRules.map((rule) => (
              <li
                key={rule}
                className="flex items-start gap-2 rounded-2xl border border-slate-100 bg-white px-3 py-2 text-xs leading-5 text-slate-600"
              >
                <MissionControlGlyph name="target" className="mt-0.5 h-3.5 w-3.5 text-violet-500" />
                <span>{rule}</span>
              </li>
            ))}
          </ul>

          <div className="mt-5 text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Patterns Used</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {graphRag.patterns.map((pattern) => (
              <span
                key={pattern}
                className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1 text-[11px] font-medium text-violet-700"
              >
                {pattern}
              </span>
            ))}
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">Impacted Files</div>
          <div className="mt-3 space-y-2">
            {graphRag.impactedFiles.map((file) => (
              <div
                key={file}
                className="flex items-center justify-between gap-3 rounded-2xl border border-slate-100 bg-slate-50 px-3 py-2.5"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <MissionControlGlyph name="file" className="h-4 w-4 shrink-0 text-slate-500" />
                  <span className="truncate text-sm font-medium text-slate-700">{file}</span>
                </div>
                <span className="rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                  in scope
                </span>
              </div>
            ))}
          </div>

          <details className="mt-5 group rounded-2xl border border-slate-200 bg-white">
            <summary className="flex cursor-pointer items-center justify-between gap-2 rounded-2xl px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 hover:text-slate-700">
              <span>Injected Context (raw)</span>
              <MissionControlGlyph name="arrow" className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
            </summary>
            <pre className="mission-code-block overflow-x-auto whitespace-pre-wrap break-words rounded-b-2xl border-t border-slate-100 p-4 text-[11.5px] leading-5 text-slate-700">
              {graphRag.injectedContext}
            </pre>
          </details>
        </div>
      </div>
    </div>
  )
}
