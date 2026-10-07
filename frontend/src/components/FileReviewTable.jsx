import StatusBadge from "./StatusBadge"
import { MissionControlGlyph } from "./MissionControlIcons"

function statusTone(status) {
  if (status === "Accepted") return "success"
  if (status === "Rejected") return "failed"
  if (status === "Needs Improvement") return "warning"
  return "info"
}

export default function FileReviewTable({ rows, onAction }) {
  return (
    <div className="overflow-hidden rounded-[24px] border border-slate-100 bg-white">
      <div className="overflow-x-auto">
        <div className="min-w-[920px]">
          <div className="grid grid-cols-[minmax(220px,1.6fr)_minmax(90px,0.7fr)_minmax(190px,1.1fr)_minmax(360px,1.6fr)] gap-4 bg-slate-50 px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
            <div>File</div>
            <div>Type</div>
            <div>Review Status</div>
            <div>Actions</div>
          </div>
          <div className="divide-y divide-slate-100 bg-white">
            {rows.map((row) => (
              <div
                key={row.file}
                className="grid grid-cols-[minmax(220px,1.6fr)_minmax(90px,0.7fr)_minmax(190px,1.1fr)_minmax(360px,1.6fr)] items-start gap-4 px-4 py-4"
              >
                <div className="flex min-w-0 items-start gap-3">
                  <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-slate-50 text-slate-500">
                    <MissionControlGlyph name="file" className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 whitespace-normal break-words text-sm font-medium text-slate-900">{row.file}</div>
                </div>
                <div className="pt-2 text-sm text-slate-500">{row.type}</div>
                <div className="min-w-0 pt-1">
                  <StatusBadge status={statusTone(row.status)} className="max-w-full">
                    {row.status}
                  </StatusBadge>
                </div>
                <div className="flex min-w-0 flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onAction?.("accept", row)}
                    className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={row.status === "Accepted"}
                  >
                    <MissionControlGlyph name="success" className="h-3 w-3" />
                    Accept
                  </button>
                  <button
                    type="button"
                    onClick={() => onAction?.("reject", row)}
                    className="inline-flex items-center gap-1 rounded-full border border-rose-200 bg-white px-3 py-1.5 text-xs font-medium text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={row.status === "Rejected"}
                  >
                    <MissionControlGlyph name="failed" className="h-3 w-3" />
                    Reject
                  </button>
                  <button
                    type="button"
                    onClick={() => onAction?.("changes", row)}
                    className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={row.status === "Needs Improvement"}
                  >
                    <MissionControlGlyph name="warning" className="h-3 w-3" />
                    Request Changes
                  </button>
                  <button
                    type="button"
                    onClick={() => onAction?.("diff", row)}
                    className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50"
                  >
                    <MissionControlGlyph name="file" className="h-3 w-3" />
                    View Diff
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
