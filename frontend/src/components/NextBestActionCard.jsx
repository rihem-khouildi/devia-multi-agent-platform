import { MissionControlGlyph } from "./MissionControlIcons"

export default function NextBestActionCard({ actions }) {
  return (
    <div className="space-y-3">
      <div className="rounded-[24px] border border-indigo-100 bg-[linear-gradient(160deg,_#eef2ff_0%,_#ffffff_100%)] p-4">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-indigo-600">
          <MissionControlGlyph name="target" className="h-3.5 w-3.5" />
          Next Best Action
        </div>
        <p className="mt-2 text-sm leading-6 text-slate-700">
          What a human reviewer should do <span className="font-semibold">right now</span> to unblock the run.
        </p>
      </div>

      <ol className="space-y-3">
        {actions.map((action, index) => (
          <li
            key={action.title}
            className="rounded-[22px] border border-slate-100 bg-white p-4 shadow-sm"
          >
            <div className="flex items-start gap-3">
              <div
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl text-sm font-semibold ${
                  index === 0
                    ? "bg-[linear-gradient(135deg,_#5B5CFF_0%,_#00AEEF_100%)] text-white shadow-[0_10px_24px_rgba(91,92,255,0.3)]"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {index + 1}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-900">{action.title}</div>
                <p className="mt-1 text-xs leading-5 text-slate-500">{action.detail}</p>
                <div className="mt-3">
                  <button
                    type="button"
                    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold transition ${
                      action.tone === "primary"
                        ? "bg-slate-900 text-white hover:bg-slate-800"
                        : "border border-slate-200 bg-white text-slate-700 hover:border-slate-300"
                    }`}
                  >
                    <MissionControlGlyph name="arrow" className="h-3.5 w-3.5" />
                    {action.cta}
                  </button>
                </div>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
