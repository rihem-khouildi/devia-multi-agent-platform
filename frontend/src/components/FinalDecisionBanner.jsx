import { MissionControlGlyph } from "./MissionControlIcons"

export default function FinalDecisionBanner({ runSummary, microcopy, onReplay, onOpenStory, replayActive = false }) {
  const blocked = runSummary.repository_status === "protected"

  return (
    <section
      className={`relative overflow-hidden rounded-[34px] border px-6 py-7 sm:px-8 ${
        blocked
          ? "border-rose-200/70 bg-[radial-gradient(circle_at_top_left,_rgba(244,63,94,0.18),_transparent_55%),linear-gradient(135deg,_#fff1f2_0%,_#fef2f2_45%,_#ffffff_100%)]"
          : "border-emerald-200/70 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.18),_transparent_55%),linear-gradient(135deg,_#ecfdf5_0%,_#f0fdf4_45%,_#ffffff_100%)]"
      }`}
    >
      <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-white/60 blur-3xl" aria-hidden="true" />
      <div className="absolute -bottom-32 -left-12 h-80 w-80 rounded-full bg-rose-200/30 blur-3xl" aria-hidden="true" />

      <div className="relative flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-start gap-5">
          <div
            className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-3xl text-white shadow-[0_18px_40px_rgba(15,23,42,0.18)] ${
              blocked
                ? "bg-[linear-gradient(135deg,_#f43f5e_0%,_#b91c1c_100%)]"
                : "bg-[linear-gradient(135deg,_#10b981_0%,_#059669_100%)]"
            }`}
          >
            <MissionControlGlyph name={blocked ? "lock" : "shield"} className="h-8 w-8" />
          </div>
          <div className="min-w-0">
            <div
              className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] ${
                blocked
                  ? "bg-rose-100 text-rose-700"
                  : "bg-emerald-100 text-emerald-700"
              }`}
            >
              <MissionControlGlyph name="sparkle" className="h-3.5 w-3.5" />
              Final Decision
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900 sm:text-[1.7rem]">
              {blocked ? "Validation Blocked by Quality Gate" : "Validation Passed — Ready to Merge"}
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-slate-600">
              {blocked
                ? `Repository protected — ${microcopy?.nextActionFriendly || "manual test improvement required"}. Devia refused to push low-confidence code to GitHub.`
                : "All quality gates cleared. Devia signed off the autonomous run for delivery."}
            </p>

            <div className="mt-4 flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/80 px-3 py-1.5 font-medium text-slate-600">
                <MissionControlGlyph name="run" className="h-3.5 w-3.5 text-slate-500" />
                {runSummary.run_id}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/80 px-3 py-1.5 font-medium text-slate-600">
                <MissionControlGlyph name="stories" className="h-3.5 w-3.5 text-slate-500" />
                Story {runSummary.story_id}
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 font-semibold ${
                  blocked ? "bg-rose-600/95 text-white" : "bg-emerald-600/95 text-white"
                }`}
              >
                <MissionControlGlyph name={blocked ? "blocked" : "success"} className="h-3.5 w-3.5" />
                {blocked ? "GitHub push blocked" : "GitHub push approved"}
              </span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-3 lg:justify-end">
          {onReplay ? (
            <button
              type="button"
              onClick={onReplay}
              disabled={replayActive}
              className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white shadow-[0_18px_40px_rgba(15,23,42,0.22)] transition hover:-translate-y-0.5 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <MissionControlGlyph name="replay" className={`h-4 w-4 ${replayActive ? "animate-spin" : ""}`} />
              {replayActive ? "Replaying…" : "Replay run"}
            </button>
          ) : null}
          {onOpenStory ? (
            <button
              type="button"
              onClick={onOpenStory}
              className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:text-slate-900"
            >
              <MissionControlGlyph name="book" className="h-4 w-4" />
              View execution story
            </button>
          ) : null}
        </div>
      </div>
    </section>
  )
}
