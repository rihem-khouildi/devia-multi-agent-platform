import { MissionControlGlyph } from "./MissionControlIcons"

export default function WhyBlockedCard({ runSummary }) {
  const points = [
    {
      icon: "success",
      tone: "text-emerald-600",
      label: "Compilation passed",
      detail: "Maven built the generated Spring Boot artifacts without errors.",
    },
    {
      icon: "success",
      tone: "text-emerald-600",
      label: "Tests passed",
      detail: "All 18 generated tests executed successfully via Surefire.",
    },
    {
      icon: "warning",
      tone: "text-amber-600",
      label: `Coverage ${runSummary.coverage} (required ${runSummary.required})`,
      detail: "JaCoCo reported insufficient branch coverage on the authentication path.",
    },
    {
      icon: "lock",
      tone: "text-rose-600",
      label: "GitHub push blocked",
      detail: "Devia refuses to publish low-confidence code to the protected branch.",
    },
  ]

  return (
    <div className="space-y-4">
      <div className="rounded-[24px] border border-rose-100 bg-[linear-gradient(160deg,_#fff1f2_0%,_#ffffff_100%)] p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-rose-100 text-rose-600">
            <MissionControlGlyph name="help" className="h-5 w-5" />
          </div>
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-rose-500">
              Responsible AI
            </div>
            <h3 className="mt-1 text-base font-semibold text-slate-900">Why was the GitHub push blocked?</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Compilation and tests passed, but coverage is below the required threshold. Devia prevents
              low-confidence code from being pushed automatically — the repository stays in a known-good state.
            </p>
          </div>
        </div>
      </div>

      <ul className="space-y-2">
        {points.map((point) => (
          <li
            key={point.label}
            className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-white px-3.5 py-3 shadow-sm"
          >
            <MissionControlGlyph name={point.icon} className={`mt-0.5 h-5 w-5 shrink-0 ${point.tone}`} />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-slate-900">{point.label}</div>
              <div className="mt-0.5 text-xs leading-5 text-slate-500">{point.detail}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
