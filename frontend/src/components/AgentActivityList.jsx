import StatusBadge from "./StatusBadge"

export default function AgentActivityList({ items }) {
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.name} className="rounded-[24px] border border-slate-100 bg-slate-50/90 p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h3 className="text-sm font-semibold text-slate-900">{item.name}</h3>
                <StatusBadge status="success">{item.status}</StatusBadge>
              </div>
              <div className="mt-3 grid gap-2 text-sm text-slate-500">
                <p><span className="font-medium text-slate-700">Input:</span> {item.input}</p>
                <p><span className="font-medium text-slate-700">{item.outcomeLabel}:</span> {item.outcome}</p>
              </div>
            </div>
            <div className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
              {item.time}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
