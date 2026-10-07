export default function DiagnosticsPanel({ diagnostics, onView }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-[22px] border border-rose-100 bg-rose-50 px-4 py-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-rose-400">Failed Stage</div>
          <div className="mt-2 text-sm font-semibold text-rose-700">{diagnostics.failedStage}</div>
        </div>
        <div className="rounded-[22px] border border-amber-100 bg-amber-50 px-4 py-4">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-500">Category</div>
          <div className="mt-2 text-sm font-semibold text-amber-700">{diagnostics.category}</div>
        </div>
        <div className="rounded-[22px] border border-slate-100 bg-slate-50 px-4 py-4 md:col-span-2">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Message</div>
          <div className="mt-2 text-sm leading-6 text-slate-700">{diagnostics.message}</div>
        </div>
        <div className="rounded-[22px] border border-slate-100 bg-white px-4 py-4 md:col-span-2">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Suggested Action</div>
          <div className="mt-2 text-sm leading-6 text-slate-700">{diagnostics.suggestedAction}</div>
        </div>
      </div>
      {onView ? (
        <button
          type="button"
          onClick={onView}
          className="w-full rounded-2xl border border-slate-200 bg-slate-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 lg:w-auto"
        >
          View Diagnostics
        </button>
      ) : null}
    </div>
  )
}
