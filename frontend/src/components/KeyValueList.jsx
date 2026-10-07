import StatusBadge from "./StatusBadge"

export default function KeyValueList({ items }) {
  return (
    <div className="grid gap-3">
      {items.map((item) => (
        <div
          key={item.key}
          className="grid gap-2 rounded-2xl border border-slate-100 bg-slate-50/90 px-4 py-3 md:grid-cols-[160px_minmax(0,1fr)] md:items-start lg:grid-cols-[190px_minmax(0,1fr)]"
        >
          <div className="break-words text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{item.label}</div>
          <div className="flex min-w-0 flex-wrap items-start gap-2 overflow-visible whitespace-normal break-words">
            {item.badgeStatus ? (
              <StatusBadge status={item.badgeStatus} className="max-w-full">
                {item.value}
              </StatusBadge>
            ) : (
              <span className={`max-w-full whitespace-normal break-words text-sm font-medium ${item.emphasis ? "text-slate-900" : "text-slate-600"}`}>
                {item.value}
              </span>
            )}
            {item.helper ? <span className="max-w-full whitespace-normal break-words text-xs text-slate-400">{item.helper}</span> : null}
          </div>
        </div>
      ))}
    </div>
  )
}
